import asyncio
import sqlite3
import threading
import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.collectors.westock import WeStockProvider
from backend.config import get_config
from backend.services.asset_service import AssetService
from backend.storage.database import get_db
from backend.utils import build_fund_flow_summary

# 全局并发信号量：限制同一时间并发写入 sqlite 的协程数。
# sqlite3 同步连接在同一进程内不支持多协程并发写，必须用 lock 串行化写入操作。
# 用 threading.Lock 替代 asyncio.Lock：scheduler tick 用 asyncio.run() 每次创建新
# event loop，asyncio.Lock() 首次 acquire 时绑定循环会失效；threading.Lock 跨循环安全。
_WRITE_LOCK: threading.Lock = threading.Lock()


class CollectionService:
    """数据采集编排服务，负责调度 Provider 采集数据并持久化。"""

    def __init__(self, providers: dict[str, list[BaseProvider]] | None = None) -> None:
        if providers is not None:
            self._providers = providers
        else:
            config = get_config()
            self._providers = create_providers(config)
        self._asset_service = AssetService(providers=self._providers)

    def _get_structured_providers(self) -> list[BaseProvider]:
        return self._providers.get("structured", [])

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _save_raw_data(
        conn: sqlite3.Connection,
        symbol: str,
        source: str,
        data_type: str,
        raw_json: str,
        collected_at: str,
    ) -> None:
        conn.execute(
            """INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol, source, data_type, raw_json, collected_at),
        )

    @staticmethod
    def _write_run_log(
        conn: sqlite3.Connection,
        task_name: str,
        status: str,
        started_at: str,
        finished_at: str,
        error_message: str | None,
        affected_assets: int,
    ) -> None:
        conn.execute(
            """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_name, status, started_at, finished_at, error_message, affected_assets),
        )

    async def _collect_quote_for_symbol(
        self, write_lock: threading.Lock, symbol: str
    ) -> dict | None:
        """采集单个标的的最新行情。

        注意：sqlite3 同步连接不支持多协程并发写，因此用 write_lock 串行化写入。
        采集请求（IO）可并发，但所有 INSERT 必须互斥。
        """
        for provider in self._get_structured_providers():
            try:
                results = await provider.quote([symbol])
                if not results:
                    continue
                matched = [r for r in results if r.get("symbol") == symbol]
                if not matched:
                    continue
                item = matched[0]
                raw_json = json.dumps(item, ensure_ascii=False, default=str)
                collected_at = item.get("collected_at", self._now_iso())
                source = item.get("source", provider.name)
                # 写入阶段加锁，保证多协程串行化 INSERT
                with write_lock:
                    from backend.storage.database import get_connection_sync
                    conn = get_connection_sync()
                    try:
                        self._save_raw_data(conn, symbol, source, "quote", raw_json, collected_at)
                        conn.execute(
                            """INSERT OR IGNORE INTO market_quotes
                               (symbol, price, change, change_pct, open, high, low, prev_close,
                                volume, amount, amplitude, turnover_rate, high_52w, low_52w, source, collected_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                symbol,
                                item.get("price"),
                                item.get("change"),
                                item.get("change_pct"),
                                item.get("open"),
                                item.get("high"),
                                item.get("low"),
                                item.get("prev_close"),
                                item.get("volume"),
                                item.get("amount"),
                                item.get("amplitude"),
                                item.get("turnover_rate"),
                                item.get("high_52w"),
                                item.get("low_52w"),
                                source,
                                collected_at,
                            ),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                return item
            except Exception as e:
                logger.warning("Provider {} 采集行情失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_quotes(self) -> dict:
        """并发采集所有启用标的的最新行情。

        使用 Semaphore(10) 限制同时并发请求数；写入侧用 write_lock 串行化。
        """
        started_at = self._now_iso()
        assets = self._asset_service.get_active_assets()
        total = len(assets)
        write_lock = _WRITE_LOCK
        sem = asyncio.Semaphore(10)
        errors: list[str] = []

        async def _run_one(asset: dict) -> bool:
            symbol: str = asset["symbol"]
            try:
                async with sem:
                    item = await self._collect_quote_for_symbol(write_lock, symbol)
                return item is not None
            except Exception as e:
                logger.warning("采集 {} 行情异常: {}", symbol, e)
                return False

        results = await asyncio.gather(
            *[_run_one(asset) for asset in assets], return_exceptions=False
        )

        success = sum(1 for ok in results if ok)
        failed = total - success
        for asset, ok in zip(assets, results):
            if not ok:
                errors.append(f"{asset['symbol']}: 所有数据源均失败")

        finished_at = self._now_iso()
        status = "success" if failed == 0 else "failure"
        error_message = "; ".join(errors) if errors else None
        with get_db() as conn:
            self._write_run_log(conn, "quote", status, started_at, finished_at, error_message, total)

        return {"success": success, "failed": failed, "total": total}

    async def collect_quote_single(self, symbol: str) -> dict | None:
        write_lock = _WRITE_LOCK
        return await self._collect_quote_for_symbol(write_lock, symbol)

    async def collect_daily_close(self) -> dict:
        """并发采集所有启用标的的日终七类数据。

        同一标的的 7 个数据源并行；不同标的间用 Semaphore(10) 限制并发。
        """
        started_at = self._now_iso()
        assets = self._asset_service.get_active_assets()
        summary: dict[str, dict[str, int]] = {
            "kline": {"success": 0, "failed": 0},
            "finance": {"success": 0, "failed": 0},
            "fund_flow": {"success": 0, "failed": 0},
            "technical": {"success": 0, "failed": 0},
            "dividend": {"success": 0, "failed": 0},
            "shareholder": {"success": 0, "failed": 0},
            "reserve": {"success": 0, "failed": 0},
        }
        all_errors: list[str] = []
        write_lock = _WRITE_LOCK
        sem = asyncio.Semaphore(10)

        async def _run_one(asset: dict) -> dict:
            symbol: str = asset["symbol"]
            async with sem:
                return await self._collect_daily_close_for_symbol(write_lock, symbol)

        per_symbol_results = await asyncio.gather(
            *[_run_one(asset) for asset in assets], return_exceptions=True
        )

        for asset, result in zip(assets, per_symbol_results):
            if isinstance(result, Exception):
                logger.warning("采集 {} 失败: {}", asset["symbol"], result)
                all_errors.append(f"{asset['symbol']}: {result}")
                for k in summary:
                    summary[k]["failed"] += 1
                continue
            for k, v in result["summary"].items():
                summary[k]["success"] += v["success"]
                summary[k]["failed"] += v["failed"]
            all_errors.extend(result["errors"])

        finished_at = self._now_iso()
        status = "success" if not all_errors else "failure"
        error_message = "; ".join(all_errors) if all_errors else None
        affected = len(assets)
        with get_db() as conn:
            self._write_run_log(conn, "daily_close", status, started_at, finished_at, error_message, affected)

        return summary

    async def _fetch_kline(self, symbol: str) -> dict:
        """仅执行网络 IO，不写库；返回数据 + 计数供上层 commit 阶段落盘。

        拆分目的：与 _insert_kline 配合，让 4 类数据可在无 write_lock 下并行 fetch，
        然后在持锁阶段一次性 commit（避免 IO 持锁阻塞其他标的的写）。
        """
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []  # (source, raw_json, collected_at)
        for provider in self._get_structured_providers():
            try:
                items = await provider.kline(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append((
                        symbol,
                        item.get("date"),
                        item.get("open"),
                        item.get("high"),
                        item.get("low"),
                        item.get("close"),
                        item.get("volume"),
                        item.get("change_pct"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集K线失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    def _insert_kline(self, conn: sqlite3.Connection, payload: dict) -> None:
        """纯同步落盘，由 commit 阶段在 write_lock 内调用。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "kline", raw_json, collected_at)
        for row in payload["rows"]:
            conn.execute(
                """INSERT OR IGNORE INTO kline_daily
                   (symbol, date, open, high, low, close, volume, change_pct, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )

    async def _fetch_finance(self, symbol: str) -> dict:
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                data = await provider.finance(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                report_period = data.get("report_period") or data.get("period") or data.get("report_date")
                row = (
                    symbol,
                    report_period,
                    data.get("revenue"),
                    data.get("revenue_yoy"),
                    data.get("net_profit"),
                    data.get("net_profit_yoy"),
                    data.get("eps"),
                    data.get("roe"),
                    data.get("debt_ratio"),
                    data.get("gross_margin"),
                    data.get("net_margin"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集财务数据失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    def _insert_finance(self, conn: sqlite3.Connection, payload: dict) -> None:
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "finance", raw_json, collected_at)
        if payload["row"] is not None:
            conn.execute(
                """INSERT OR IGNORE INTO financial_reports
                   (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
                    eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload["row"],
            )

    async def _fetch_fund_flow(self, symbol: str) -> dict:
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                data = await provider.fund_flow(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                item = data
                row = (
                    symbol,
                    item.get("date"),
                    item.get("main_net_inflow") or item.get("net_flow"),
                    item.get("super_large_net_inflow"),
                    item.get("large_net_inflow") or item.get("main_inflow"),
                    item.get("medium_net_inflow"),
                    item.get("small_net_inflow"),
                    item.get("net_inflow_ratio"),
                    item.get("source", source),
                    item.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集资金流向失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    def _insert_fund_flow(self, conn: sqlite3.Connection, payload: dict) -> None:
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "fund_flow", raw_json, collected_at)
        if payload["row"] is not None:
            conn.execute(
                """INSERT OR IGNORE INTO fund_flows
                   (symbol, date, main_net_inflow, super_large_net_inflow, large_net_inflow,
                    medium_net_inflow, small_net_inflow, net_inflow_ratio, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload["row"],
            )

    async def _fetch_technical(self, symbol: str) -> dict:
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                data = await provider.technical(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("ma5"),
                    data.get("ma10"),
                    data.get("ma20"),
                    data.get("ma60"),
                    data.get("macd_dif"),
                    data.get("macd_dea"),
                    data.get("macd_histogram"),
                    data.get("rsi6"),
                    data.get("rsi14"),
                    data.get("boll_upper"),
                    data.get("boll_middle"),
                    data.get("boll_lower"),
                    data.get("volume_ma5"),
                    data.get("volume_ma20"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集技术指标失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    def _insert_technical(self, conn: sqlite3.Connection, payload: dict) -> None:
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "technical", raw_json, collected_at)
        if payload["row"] is not None:
            conn.execute(
                """INSERT OR IGNORE INTO technical_indicators
                   (symbol, date, ma5, ma10, ma20, ma60,
                    macd_dif, macd_dea, macd_histogram,
                    rsi6, rsi14, boll_upper, boll_middle, boll_lower,
                    volume_ma5, volume_ma20, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload["row"],
            )

    async def _fetch_dividend(self, symbol: str) -> dict:
        """仅网络 IO，不写库；返回分红记录 + 计数供上层落盘。

        拆分目的：与 _insert_dividends 配合，让 fetch 与 commit 解耦。
        """
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                items = await provider.dividend(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    # dividend_year 在 westock 输出是字符串如 "2023"，_try_number 已转 int
                    year_val = item.get("dividend_year")
                    if not isinstance(year_val, int):
                        try:
                            year_val = int(str(year_val).strip()) if year_val is not None and str(year_val).strip() else None
                        except (ValueError, TypeError):
                            year_val = None
                    rows.append((
                        symbol,
                        item.get("ex_date", ""),
                        item.get("cash_dividend"),
                        item.get("share_bonus"),
                        item.get("record_date"),
                        item.get("announce_date"),
                        year_val,
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集分红失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    def _insert_dividends(self, conn: sqlite3.Connection, payload: dict) -> int:
        """批量插入分红记录，INSERT OR IGNORE 去重。

        Returns: 实际写入行数（SQLite executemany 的 rowcount）。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "dividend", raw_json, collected_at)
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO dividends
               (symbol, ex_date, cash_dividend, share_bonus,
                record_date, announce_date, dividend_year, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    async def _fetch_reserve(self, symbol: str) -> dict:
        """仅网络 IO，不写库；返回业绩预告 + 计数供上层落盘。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                data = await provider.reserve(symbol)
                # 正常返回空 dict 时跳过（westock 约定空数据返回占位 dict）
                if not data or not data.get("report_period"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                # forecast_type 是 NOT NULL；缺失时填 "未知" 防止约束失败
                forecast_type = data.get("forecast_type") or "未知"
                row = (
                    symbol,
                    data.get("report_period"),
                    forecast_type,
                    data.get("profit_lower"),
                    data.get("profit_upper"),
                    data.get("change_lower"),
                    data.get("change_upper"),
                    data.get("summary"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集业绩预告失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    def _insert_profit_forecasts(self, conn: sqlite3.Connection, payload: dict) -> int:
        """单条业绩预告插入，INSERT OR IGNORE 去重。

        Returns: 实际写入行数（0 或 1）。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "reserve", raw_json, collected_at)
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO profit_forecasts
               (symbol, report_period, forecast_type, profit_lower, profit_upper,
                change_lower, change_upper, summary, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    async def _fetch_shareholder(self, symbol: str) -> dict:
        """仅网络 IO，不写库；返回股东结构 + 股东户数历史 + 计数供上层落盘。

        返回 dict 同时含 top_shareholders 行列表与 holder_count_history 行列表，
        由 _insert_shareholders 一次性 commit 到两张表（事务一致性）。
        """
        success = 0
        failed = 0
        top_rows: list[tuple] = []
        count_rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                data = await provider.shareholder(symbol)
                if not data or not data.get("top_shareholders"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                # westock 股东表每行无 report_period 字段；CLI 输出通常带 EndDate
                # 若规范数据无 period 字段则用 collected_at 作占位，确保 UNIQUE 不冲突
                report_period_fallback = data.get("report_period") or data.get("end_date") or collected_at
                for sh in data["top_shareholders"]:
                    top_rows.append((
                        symbol,
                        report_period_fallback,
                        sh.get("rank"),
                        sh.get("name"),
                        sh.get("shares"),
                        sh.get("ratio"),
                        sh.get("change"),  # 对应 shareholders.change_amount
                        data.get("source", source),
                        data.get("collected_at", collected_at),
                    ))
                for hc in data.get("holder_count_history", []):
                    count_rows.append((
                        symbol,
                        hc.get("date", ""),
                        hc.get("total_holders"),
                        hc.get("avg_shares"),
                        data.get("source", source),
                        data.get("collected_at", collected_at),
                    ))
                success = len(data["top_shareholders"])
                break
            except Exception as e:
                logger.warning("Provider {} 采集股东结构失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "top_rows": top_rows,
            "count_rows": count_rows,
            "raw_packets": raw_packets,
        }

    def _insert_shareholders(
        self, conn: sqlite3.Connection, payload: dict
    ) -> tuple[int, int]:
        """股东结构 + 股东户数历史 双表单事务落盘。

        两张表共用同一份原始 raw_data + collected_at；为保证两张表数据一致性，
        必须在同一 connection、同一 commit 中写入（任一 executemany 抛错时整体回滚）。

        Returns: (top_inserted, count_inserted) 行数元组。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            self._save_raw_data(conn, payload["symbol"], source, "shareholder", raw_json, collected_at)
        top_inserted = 0
        if payload["top_rows"]:
            cur = conn.executemany(
                """INSERT OR IGNORE INTO shareholders
                   (symbol, report_period, rank, name, shares, ratio, change_amount,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload["top_rows"],
            )
            top_inserted = cur.rowcount
        count_inserted = 0
        if payload["count_rows"]:
            cur = conn.executemany(
                """INSERT OR IGNORE INTO shareholder_count_history
                   (symbol, report_date, total_holders, avg_shares, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                payload["count_rows"],
            )
            count_inserted = cur.rowcount
        return top_inserted, count_inserted

    async def _collect_daily_close_for_symbol(
        self, write_lock: threading.Lock, symbol: str
    ) -> dict:
        """采集单标的的 K线/财务/资金流向/技术指标 + 分红/股东/业绩预告。

        同一标的的 7 个数据源相互独立，可并行；不同标的间用 Semaphore 限制并发数。
        写入侧用 write_lock 串行化：先并发 fetch（无锁网络 IO），再持锁一次性 commit。
        """
        results: dict[str, dict] = {
            "kline": {"success": 0, "failed": 0},
            "finance": {"success": 0, "failed": 0},
            "fund_flow": {"success": 0, "failed": 0},
            "technical": {"success": 0, "failed": 0},
            "dividend": {"success": 0, "failed": 0},
            "shareholder": {"success": 0, "failed": 0},
            "reserve": {"success": 0, "failed": 0},
        }
        errors: list[str] = []

        # 阶段 1：7 类数据并行 fetch（不持锁，纯网络 IO，事件循环可调度其他协程）
        try:
            (
                kline_p,
                finance_p,
                fund_p,
                tech_p,
                dividend_p,
                shareholder_p,
                reserve_p,
            ) = await asyncio.gather(
                self._fetch_kline(symbol),
                self._fetch_finance(symbol),
                self._fetch_fund_flow(symbol),
                self._fetch_technical(symbol),
                self._fetch_dividend(symbol),
                self._fetch_shareholder(symbol),
                self._fetch_reserve(symbol),
            )
        except Exception as e:
            logger.exception("daily_close fetch 阶段失败: symbol={}", symbol)
            return {"summary": results, "errors": [f"{symbol}: fetch 异常 {e}"]}

        for name, payload in [
            ("kline", kline_p),
            ("finance", finance_p),
            ("fund_flow", fund_p),
            ("technical", tech_p),
            ("dividend", dividend_p),
            ("shareholder", shareholder_p),
            ("reserve", reserve_p),
        ]:
            results[name]["success"] = payload["success"]
            results[name]["failed"] = payload["failed"]

        # 阶段 2：持锁 commit。锁内仅做同步 DB 写入（毫秒级），不再持有网络 IO。
        from backend.storage.database import get_connection_sync
        try:
            with write_lock:
                conn = get_connection_sync()
                try:
                    self._insert_kline(conn, {"symbol": symbol, **kline_p})
                    self._insert_finance(conn, {"symbol": symbol, **finance_p})
                    self._insert_fund_flow(conn, {"symbol": symbol, **fund_p})
                    self._insert_technical(conn, {"symbol": symbol, **tech_p})
                    # 新增三张表：分红/股东结构/业绩预告
                    self._insert_dividends(conn, {"symbol": symbol, **dividend_p})
                    self._insert_shareholders(conn, {"symbol": symbol, **shareholder_p})
                    self._insert_profit_forecasts(conn, {"symbol": symbol, **reserve_p})
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("daily_close commit 阶段失败: symbol={}", symbol)
            for name in results:
                if results[name]["success"] > 0:
                    results[name]["failed"] += results[name]["success"]
                    results[name]["success"] = 0
                    errors.append(f"{symbol}/{name}: commit 失败 {e}")

        return {"summary": results, "errors": errors}


    async def collect_intraday(self, symbol: str, days: int = 1) -> list[dict] | None:
        """实时采集分时数据并落库。

        注：分时数据按需触发（API 主动调用），不在 daily_close 编排中拉取。
        """
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.minute(symbol, days=days)
                if items:
                    # 落库：持锁 + executemany INSERT OR IGNORE
                    rows: list[tuple] = []
                    for item in items:
                        rows.append((
                            symbol,
                            item.get("time", ""),
                            item.get("price"),
                            item.get("volume"),
                            item.get("avg_price"),
                            item.get("source", provider.name),
                            item.get("collected_at", self._now_iso()),
                        ))
                    from backend.storage.database import get_connection_sync
                    with _WRITE_LOCK:
                        conn = get_connection_sync()
                        try:
                            raw_json = json.dumps(items, ensure_ascii=False, default=str)
                            self._save_raw_data(
                                conn, symbol, provider.name, "minute",
                                raw_json, self._now_iso(),
                            )
                            conn.executemany(
                                """INSERT OR IGNORE INTO minute_klines
                                   (symbol, time, price, volume, avg_price, source, collected_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                rows,
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    return items
            except Exception as e:
                logger.warning("Provider {} 采集分时失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_shareholder(self, symbol: str) -> dict | None:
        """实时采集股东结构数据并落库（双表单事务）。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                result = await provider.shareholder(symbol)
                if result and result.get("top_shareholders"):
                    # 落库：单事务双表
                    collected_at = self._now_iso()
                    source = provider.name
                    report_period_fallback = (
                        result.get("report_period")
                        or result.get("end_date")
                        or collected_at
                    )
                    top_rows: list[tuple] = []
                    for sh in result["top_shareholders"]:
                        top_rows.append((
                            symbol,
                            report_period_fallback,
                            sh.get("rank"),
                            sh.get("name"),
                            sh.get("shares"),
                            sh.get("ratio"),
                            sh.get("change"),
                            result.get("source", source),
                            result.get("collected_at", collected_at),
                        ))
                    count_rows: list[tuple] = []
                    for hc in result.get("holder_count_history", []):
                        count_rows.append((
                            symbol,
                            hc.get("date", ""),
                            hc.get("total_holders"),
                            hc.get("avg_shares"),
                            result.get("source", source),
                            result.get("collected_at", collected_at),
                        ))
                    from backend.storage.database import get_connection_sync
                    with _WRITE_LOCK:
                        conn = get_connection_sync()
                        try:
                            raw_json = json.dumps(result, ensure_ascii=False, default=str)
                            self._save_raw_data(
                                conn, symbol, source, "shareholder",
                                raw_json, collected_at,
                            )
                            if top_rows:
                                conn.executemany(
                                    """INSERT OR IGNORE INTO shareholders
                                       (symbol, report_period, rank, name, shares, ratio, change_amount,
                                        source, collected_at)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    top_rows,
                                )
                            if count_rows:
                                conn.executemany(
                                    """INSERT OR IGNORE INTO shareholder_count_history
                                       (symbol, report_date, total_holders, avg_shares, source, collected_at)
                                       VALUES (?, ?, ?, ?, ?, ?)""",
                                    count_rows,
                                )
                            conn.commit()
                        finally:
                            conn.close()
                    return result
            except Exception as e:
                logger.warning("Provider {} 采集股东结构失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_reserve(self, symbol: str) -> dict | None:
        """实时采集业绩预告并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                result = await provider.reserve(symbol)
                if result and result.get("report_period"):
                    # 落库：单条 INSERT OR IGNORE
                    forecast_type = result.get("forecast_type") or "未知"
                    collected_at = self._now_iso()
                    source = provider.name
                    from backend.storage.database import get_connection_sync
                    with _WRITE_LOCK:
                        conn = get_connection_sync()
                        try:
                            raw_json = json.dumps(result, ensure_ascii=False, default=str)
                            self._save_raw_data(
                                conn, symbol, source, "reserve",
                                raw_json, collected_at,
                            )
                            conn.execute(
                                """INSERT OR IGNORE INTO profit_forecasts
                                   (symbol, report_period, forecast_type, profit_lower, profit_upper,
                                    change_lower, change_upper, summary, source, collected_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    symbol,
                                    result.get("report_period"),
                                    forecast_type,
                                    result.get("profit_lower"),
                                    result.get("profit_upper"),
                                    result.get("change_lower"),
                                    result.get("change_upper"),
                                    result.get("summary"),
                                    result.get("source", source),
                                    result.get("collected_at", collected_at),
                                ),
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    return result
            except Exception as e:
                logger.warning("Provider {} 采集业绩预告失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_dividend(self, symbol: str) -> list[dict] | None:
        """实时采集分红记录并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.dividend(symbol)
                if items:
                    # 落库：executemany INSERT OR IGNORE
                    collected_at = self._now_iso()
                    source = provider.name
                    rows: list[tuple] = []
                    for item in items:
                        year_val = item.get("dividend_year")
                        if not isinstance(year_val, int):
                            try:
                                year_val = (
                                    int(str(year_val).strip())
                                    if year_val is not None and str(year_val).strip()
                                    else None
                                )
                            except (ValueError, TypeError):
                                year_val = None
                        rows.append((
                            symbol,
                            item.get("ex_date", ""),
                            item.get("cash_dividend"),
                            item.get("share_bonus"),
                            item.get("record_date"),
                            item.get("announce_date"),
                            year_val,
                            item.get("source", source),
                            item.get("collected_at", collected_at),
                        ))
                    from backend.storage.database import get_connection_sync
                    with _WRITE_LOCK:
                        conn = get_connection_sync()
                        try:
                            raw_json = json.dumps(items, ensure_ascii=False, default=str)
                            self._save_raw_data(
                                conn, symbol, source, "dividend",
                                raw_json, collected_at,
                            )
                            conn.executemany(
                                """INSERT OR IGNORE INTO dividends
                                   (symbol, ex_date, cash_dividend, share_bonus,
                                    record_date, announce_date, dividend_year, source, collected_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                rows,
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    return items
            except Exception as e:
                logger.warning("Provider {} 采集分红记录失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    def get_quote(self, symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT * FROM market_quotes WHERE symbol = ? ORDER BY collected_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_quote_history(
        self,
        symbol: str,
        limit: int = 100,
        from_dt: str | None = None,
        to_dt: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_dt is not None:
            conditions.append("collected_at >= ?")
            params.append(from_dt)
        if to_dt is not None:
            conditions.append("collected_at <= ?")
            params.append(to_dt)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM market_quotes WHERE {where} ORDER BY collected_at DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_kline(
        self,
        symbol: str,
        limit: int = 60,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_date is not None:
            conditions.append("date >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("date <= ?")
            params.append(to_date)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM kline_daily WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_finance(self, symbol: str, limit: int = 4) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM financial_reports WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT ?""",
                (symbol, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_fund_flow(self, symbol: str, days: int = 5) -> dict:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM fund_flows WHERE symbol = ?
                   ORDER BY date DESC LIMIT ?""",
                (symbol, days),
            ).fetchall()
        items = [dict(row) for row in rows]
        summary = build_fund_flow_summary(items) or {
            "net_flow_5d": 0, "trend": "无数据", "avg_net_inflow_ratio": 0.0
        }
        return {"items": items, "summary": summary}

    def get_technical(self, symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT * FROM technical_indicators WHERE symbol = ?
                   ORDER BY date DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)