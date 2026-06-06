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

    @staticmethod
    def _with_run_log(task_name: str):
        """装饰器：为 collect_* 方法自动写 run_logs 行。

        - started_at / finished_at 记录 UTC
        - status: 成功且有数据 → "success"；返回 None（所有 provider 失败）→ "failure"；
                  异常 → "failure" + error_message
        - affected_assets: 1（按 symbol/market 单点调用；collect_quotes 走原路径不适用）
        """

        def decorator(coro):
            async def wrapper(self, *args, **kwargs):
                started_at = self._now_iso()
                status = "success"
                error_message: str | None = None
                result = None
                try:
                    result = await coro(self, *args, **kwargs)
                    if result is None:
                        status = "failure"
                        error_message = "所有数据源均失败"
                    return result
                except Exception as e:
                    status = "failure"
                    error_message = str(e)[:500]
                    raise
                finally:
                    finished_at = self._now_iso()
                    try:
                        with get_db() as conn:
                            self._write_run_log(
                                conn,
                                task_name,
                                status,
                                started_at,
                                finished_at,
                                error_message,
                                1,
                            )
                    except Exception as log_err:
                        logger.warning("写入 run_logs 失败: task={} err={}", task_name, log_err)

            return wrapper

        return decorator

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

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 _fetch_*（仅网络 IO，不写库）
    # ------------------------------------------------------------------

    async def _fetch_etf_info(self, symbol: str) -> dict:
        """ETF 基本信息 fetch（单条 row + raw_packets）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_info(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("etf_type"),
                    data.get("establish_date"),
                    data.get("track_index_code"),
                    data.get("track_index_name"),
                    data.get("manage_institution"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("total_mv"),
                    data.get("shares"),
                    data.get("shares_chg"),
                    data.get("nav"),
                    data.get("disc"),
                    data.get("ytd_return"),
                    data.get("return_1m"),
                    data.get("return_3m"),
                    data.get("return_6m"),
                    data.get("return_1y"),
                    data.get("return_3y"),
                    data.get("max_drawdown_1m"),
                    data.get("max_drawdown_3m"),
                    data.get("max_drawdown_6m"),
                    data.get("max_drawdown_1y"),
                    data.get("max_drawdown_3y"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 基础信息失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_etf_holdings(self, symbol: str) -> dict:
        """ETF 成分股 fetch（多行 rows）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.etf_holdings(symbol)
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
                        item.get("constituent_code", ""),
                        item.get("constituent_name"),
                        item.get("ratio"),
                        item.get("date", ""),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 成分股失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_etf_nav(self, symbol: str, start: str, end: str) -> dict:
        """ETF 历史净值 fetch（多行）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.etf_nav(symbol, start, end)
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
                        item.get("date", ""),
                        item.get("nav"),
                        item.get("nav_change"),
                        item.get("nav_change_pct"),
                        item.get("acc_nav"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 净值失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_etf_holders(self, symbol: str) -> dict:
        """ETF 持有人结构 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_holders(symbol)
                if not data or not data.get("report_date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("report_date"),
                    data.get("holder_account"),
                    data.get("individual_holder_share"),
                    data.get("individual_holder_ratio"),
                    data.get("institution_holder_share"),
                    data.get("institution_holder_ratio"),
                    data.get("top10_share"),
                    data.get("top10_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 持有人失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_chip_distribution(self, symbol: str) -> dict:
        """筹码成本 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.chip_distribution(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("chip_profit_rate"),
                    data.get("chip_avg_cost"),
                    data.get("chip_concentration_90"),
                    data.get("chip_concentration_70"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集筹码成本失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_margintrade(self, symbol: str) -> dict:
        """融资融券 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.margintrade(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("finance_value"),
                    data.get("security_value"),
                    data.get("finance_buy_value"),
                    data.get("finance_refund_value"),
                    data.get("trading_value"),
                    data.get("trading_value_dif"),
                    data.get("finance_value_dod"),
                    data.get("security_value_dod"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集融资融券失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_blocktrade(self, symbol: str, date: str) -> dict:
        """大宗交易 fetch（单只 + 日期）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.blocktrade(symbol, date)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("turnover_price"),
                    data.get("turnover_value"),
                    data.get("close_discount_rate"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集大宗交易失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_lhb(self, symbol: str, date: str) -> dict:
        """龙虎榜 fetch（单只 + 日期）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.lhb(symbol, date)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("name"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("net_buy_amount"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("reason"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集龙虎榜失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

    async def _fetch_ipo_calendar(self, market: str) -> dict:
        """新股日历 fetch（market=hk/us）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.ipo_calendar(market)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集新股日历失败: {} - {}", provider.name, market, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_exdiv_calendar(self, symbol: str) -> dict:
        """除权日历 fetch（港美单只）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.exdiv_calendar(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集除权日历失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    @staticmethod
    def _ipo_exdiv_row_tuple(item: dict, source: str, collected_at: str) -> tuple:
        """统一组装 ipo_exdiv_calendar 表的 row tuple。"""
        return (
            item.get("event_type", ""),
            item.get("event_date", ""),
            item.get("symbol"),
            item.get("name"),
            item.get("market", ""),
            item.get("stage"),
            item.get("price"),
            item.get("listing_date"),
            item.get("sgrq"),
            item.get("ssrq"),
            item.get("ex_div_date"),
            item.get("pay_date"),
            item.get("report_end_date"),
            item.get("dividend_per_share"),
            item.get("currency"),
            item.get("dividend_plan"),
            item.get("source", source),
            item.get("collected_at", collected_at),
        )

    async def _fetch_us_finance(self, symbol: str, ftype: str = "income", num: int = 4) -> dict:
        """美股财务 fetch（多期，--type income/balance/cashflow）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.us_finance(symbol, ftype=ftype, num=num)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集美股财务失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_hk_finance(self, symbol: str, ftype: str = "zhsy", num: int = 4) -> dict:
        """港股财务 fetch（多期，--type zhsy/zcfz/xjll）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.hk_finance(symbol, ftype=ftype, num=num)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集港股财务失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    @staticmethod
    def _us_finance_row_tuple(item: dict, source: str, collected_at: str) -> tuple:
        """统一组装 us_financials 表的 row tuple。"""
        return (
            item.get("symbol", ""),
            item.get("end_date", ""),
            item.get("period_type", "annual"),
            item.get("currency"),
            item.get("period_mark"),
            item.get("revenue"),
            item.get("net_income"),
            item.get("gross_profit"),
            item.get("operating_income"),
            item.get("ebitda"),
            item.get("ebit"),
            item.get("basic_eps"),
            item.get("diluted_eps"),
            item.get("total_assets"),
            item.get("total_liabilities"),
            item.get("total_equity"),
            item.get("operating_cashflow"),
            item.get("investing_cashflow"),
            item.get("financing_cashflow"),
            item.get("capex"),
            item.get("raw_json"),
            item.get("source", source),
            item.get("collected_at", collected_at),
        )

    async def _fetch_sector_board(self) -> dict:
        """板块首页 fetch：3 张表（行业涨幅/概念涨幅/行业资金流入 Top5）合并。

        返回 {"success": int, "failed": int, "rows": list[tuple], "raw_packets": list}
        无 symbol 参数（板块是全市场级别）。
        """
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.board_sectors()
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append((
                        item.get("name", ""),
                        item.get("date", ""),
                        item.get("sector_type", "industry"),
                        item.get("symbol"),
                        item.get("change_pct"),
                        item.get("turnover_rate"),
                        item.get("change_pct_5d"),
                        item.get("change_pct_20d"),
                        item.get("lead_stock"),
                        item.get("main_net_inflow"),
                        item.get("main_net_inflow_5d"),
                        item.get("up_down_ratio"),
                        item.get("rank"),
                        item.get("zxj"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集板块首页失败: {}", provider.name, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_sector_hot(self, limit: int = 10) -> dict:
        """热门板块 fetch（top N）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.hot_sectors(limit=limit)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                )
                for item in items:
                    rows.append((
                        item.get("name", ""),
                        item.get("date", ""),
                        item.get("sector_type", "industry"),
                        item.get("symbol"),
                        item.get("change_pct"),
                        item.get("turnover_rate"),
                        item.get("change_pct_5d"),
                        item.get("change_pct_20d"),
                        item.get("lead_stock"),
                        item.get("main_net_inflow"),
                        item.get("main_net_inflow_5d"),
                        item.get("up_down_ratio"),
                        item.get("rank"),
                        item.get("zxj"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集热门板块失败: {}", provider.name, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "rows": rows, "raw_packets": raw_packets}

    async def _fetch_etf_financial(self, symbol: str) -> dict:
        """ETF 资产配置 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_financial(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("total_assets"),
                    data.get("stock_ratio"),
                    data.get("bond_ratio"),
                    data.get("commodity_ratio"),
                    data.get("fund_ratio"),
                    data.get("key_asset_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 资产配置失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed, "row": row, "raw_packets": raw_packets}

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

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 _insert_* 静态方法
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_etf_basic(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "etf_basic", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_basic
               (code, date, etf_type, establish_date,
                track_index_code, track_index_name, manage_institution,
                close_price, change_pct, total_mv, shares, shares_chg,
                nav, disc, ytd_return,
                return_1m, return_3m, return_6m, return_1y, return_3y,
                max_drawdown_1m, max_drawdown_3m, max_drawdown_6m,
                max_drawdown_1y, max_drawdown_3y,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_holdings(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "etf_holdings", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO etf_holdings
               (code, constituent_code, constituent_name, ratio, date, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_nav(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "etf_nav", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO etf_nav_history
               (code, date, nav, nav_change, nav_change_pct, acc_nav, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_holders(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "etf_holders", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_holders
               (code, report_date, holder_account,
                individual_holder_share, individual_holder_ratio,
                institution_holder_share, institution_holder_ratio,
                top10_share, top10_ratio,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_chip_distribution(conn: sqlite3.Connection, payload: dict) -> int:
        """筹码成本落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "chip_distribution", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO chip_distribution
               (symbol, date, close_price, chip_profit_rate, chip_avg_cost,
                chip_concentration_90, chip_concentration_70, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_margintrade(conn: sqlite3.Connection, payload: dict) -> int:
        """融资融券落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "margintrade", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO margintrade_data
               (symbol, date, close_price, change_pct,
                finance_value, security_value, finance_buy_value, finance_refund_value,
                trading_value, trading_value_dif, finance_value_dod, security_value_dod,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_blocktrade(conn: sqlite3.Connection, payload: dict) -> int:
        """大宗交易落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "blocktrade", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO blocktrade_data
               (symbol, date, close_price, change_pct,
                turnover_price, turnover_value, close_discount_rate,
                buy_department, sell_department, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_lhb(conn: sqlite3.Connection, payload: dict) -> int:
        """龙虎榜落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "lhb", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO lhb_data
               (symbol, date, name, close_price, change_pct, net_buy_amount,
                buy_department, sell_department, reason, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_ipo_exdiv(conn: sqlite3.Connection, payload: dict) -> int:
        """港美 IPO + exdiv 统一落库（共用 ipo_exdiv_calendar 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"] or "calendar", source,
                "ipo_exdiv", raw_json, collected_at,
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO ipo_exdiv_calendar
               (event_type, event_date, symbol, name, market, stage,
                price, listing_date, sgrq, ssrq,
                ex_div_date, pay_date, report_end_date,
                dividend_per_share, currency, dividend_plan,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_us_financials(conn: sqlite3.Connection, payload: dict) -> int:
        """美股/港股财务 统一落库（共用 us_financials 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "us_financial", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO us_financials
               (symbol, end_date, period_type, currency, period_mark,
                revenue, net_income, gross_profit, operating_income,
                ebitda, ebit, basic_eps, diluted_eps,
                total_assets, total_liabilities, total_equity,
                operating_cashflow, investing_cashflow, financing_cashflow, capex,
                raw_json, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_sector_quotes(conn: sqlite3.Connection, payload: dict) -> int:
        """板块首页/热门板块 统一落库（共用 sector_daily_quote 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, "sector", source, "sector_quote", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO sector_daily_quote
               (name, date, sector_type, symbol,
                change_pct, turnover_rate, change_pct_5d, change_pct_20d,
                lead_stock, main_net_inflow, main_net_inflow_5d, up_down_ratio,
                rank, zxj, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_financial(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            CollectionService._save_raw_data(
                conn, payload["symbol"], source, "etf_financial", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_financial
               (code, date, total_assets, stock_ratio, bond_ratio,
                commodity_ratio, fund_ratio, key_asset_ratio,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

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


    @_with_run_log("intraday_refresh")
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

    @_with_run_log("shareholder_refresh")
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

    @_with_run_log("reserve_refresh")
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

    @_with_run_log("dividend_refresh")
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

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 collect_* 公开方法（手动触发采集 + 落库）
    # ------------------------------------------------------------------

    @_with_run_log("etf_info_refresh")
    async def collect_etf_info(self, symbol: str) -> dict | None:
        """采集 ETF 基本信息并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_info(symbol)
                if not data or not data.get("date"):
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date"),
                    data.get("etf_type"),
                    data.get("establish_date"),
                    data.get("track_index_code"),
                    data.get("track_index_name"),
                    data.get("manage_institution"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("total_mv"),
                    data.get("shares"),
                    data.get("shares_chg"),
                    data.get("nav"),
                    data.get("disc"),
                    data.get("ytd_return"),
                    data.get("return_1m"),
                    data.get("return_3m"),
                    data.get("return_6m"),
                    data.get("return_1y"),
                    data.get("return_3y"),
                    data.get("max_drawdown_1m"),
                    data.get("max_drawdown_3m"),
                    data.get("max_drawdown_6m"),
                    data.get("max_drawdown_1y"),
                    data.get("max_drawdown_3y"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_etf_basic(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 基础信息失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("etf_holdings_refresh")
    async def collect_etf_holdings(self, symbol: str) -> list[dict] | None:
        """采集 ETF 成分股并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.etf_holdings(symbol)
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append((
                        symbol,
                        item.get("constituent_code", ""),
                        item.get("constituent_name"),
                        item.get("ratio"),
                        item.get("date", ""),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                payload = {
                    "symbol": symbol,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_etf_holdings(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 成分股失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("etf_nav_refresh")
    async def collect_etf_nav(
        self, symbol: str, start: str, end: str
    ) -> list[dict] | None:
        """采集 ETF 历史净值并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.etf_nav(symbol, start, end)
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append((
                        symbol,
                        item.get("date", ""),
                        item.get("nav"),
                        item.get("nav_change"),
                        item.get("nav_change_pct"),
                        item.get("acc_nav"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                payload = {
                    "symbol": symbol,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_etf_nav(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 净值失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("etf_holders_refresh")
    async def collect_etf_holders(self, symbol: str) -> dict | None:
        """采集 ETF 持有人结构并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_holders(symbol)
                if not data or not data.get("report_date"):
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("report_date"),
                    data.get("holder_account"),
                    data.get("individual_holder_share"),
                    data.get("individual_holder_ratio"),
                    data.get("institution_holder_share"),
                    data.get("institution_holder_ratio"),
                    data.get("top10_share"),
                    data.get("top10_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_etf_holders(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 持有人失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("chip_distribution_refresh")
    async def collect_chip_distribution(self, symbol: str) -> dict | None:
        """采集筹码成本并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.chip_distribution(symbol)
                if not data or not data.get("date"):
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("chip_profit_rate"),
                    data.get("chip_avg_cost"),
                    data.get("chip_concentration_90"),
                    data.get("chip_concentration_70"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_chip_distribution(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集筹码成本失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("margintrade_refresh")
    async def collect_margintrade(self, symbol: str) -> dict | None:
        """采集融资融券并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.margintrade(symbol)
                if not data or not data.get("date"):
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("finance_value"),
                    data.get("security_value"),
                    data.get("finance_buy_value"),
                    data.get("finance_refund_value"),
                    data.get("trading_value"),
                    data.get("trading_value_dif"),
                    data.get("finance_value_dod"),
                    data.get("security_value_dod"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_margintrade(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集融资融券失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("blocktrade_refresh")
    async def collect_blocktrade(self, symbol: str, date: str) -> dict | None:
        """采集大宗交易并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.blocktrade(symbol, date)
                if not data:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("turnover_price"),
                    data.get("turnover_value"),
                    data.get("close_discount_rate"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_blocktrade(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集大宗交易失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("lhb_refresh")
    async def collect_lhb(self, symbol: str, date: str) -> dict | None:
        """采集龙虎榜并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.lhb(symbol, date)
                if not data:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("name"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("net_buy_amount"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("reason"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_lhb(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集龙虎榜失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("ipo_calendar_refresh")
    async def collect_ipo_calendar(self, market: str) -> list[dict] | None:
        """采集新股日历（hk/us）并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.ipo_calendar(market)
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                payload = {
                    "symbol": market,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_ipo_exdiv(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集新股日历失败: {}", provider.name, e)
                continue
        return None

    @_with_run_log("exdiv_calendar_refresh")
    async def collect_exdiv_calendar(self, symbol: str) -> list[dict] | None:
        """采集除权日历（港美）并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.exdiv_calendar(symbol)
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                payload = {
                    "symbol": symbol,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_ipo_exdiv(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集除权日历失败: {}", provider.name, e)
                continue
        return None

    @_with_run_log("us_finance_refresh")
    async def collect_us_finance(
        self, symbol: str, num: int = 4
    ) -> list[dict] | None:
        """采集美股财务（3 个 type × num 期 = 12 行）并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                all_items: list[dict] = []
                for ftype in ("income", "balance", "cashflow"):
                    items = await provider.us_finance(symbol, ftype=ftype, num=num)
                    if items:
                        all_items.extend(items)
                if not all_items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in all_items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                payload = {
                    "symbol": symbol,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(all_items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_us_financials(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return all_items
            except Exception as e:
                logger.warning("Provider {} 采集美股财务失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("hk_finance_refresh")
    async def collect_hk_finance(
        self, symbol: str, num: int = 4
    ) -> list[dict] | None:
        """采集港股财务（3 个 type × num 期 = 12 行）并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                all_items: list[dict] = []
                for ftype in ("zhsy", "zcfz", "xjll"):
                    items = await provider.hk_finance(symbol, ftype=ftype, num=num)
                    if items:
                        all_items.extend(items)
                if not all_items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in all_items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                payload = {
                    "symbol": symbol,
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(all_items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_us_financials(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return all_items
            except Exception as e:
                logger.warning("Provider {} 采集港股财务失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    @_with_run_log("sector_board_refresh")
    async def collect_sector_board(self) -> dict | None:
        """采集板块首页（3 张表）并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.board_sectors()
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append((
                        item.get("name", ""),
                        item.get("date", ""),
                        item.get("sector_type", "industry"),
                        item.get("symbol"),
                        item.get("change_pct"),
                        item.get("turnover_rate"),
                        item.get("change_pct_5d"),
                        item.get("change_pct_20d"),
                        item.get("lead_stock"),
                        item.get("main_net_inflow"),
                        item.get("main_net_inflow_5d"),
                        item.get("up_down_ratio"),
                        item.get("rank"),
                        item.get("zxj"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                payload = {
                    "symbol": "sector",
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_sector_quotes(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集板块首页失败: {}", provider.name, e)
                continue
        return None

    @_with_run_log("sector_hot_refresh")
    async def collect_sector_hot(self, limit: int = 10) -> list[dict] | None:
        """采集热门板块并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.hot_sectors(limit=limit)
                if not items:
                    return None
                collected_at = self._now_iso()
                source = provider.name
                rows: list[tuple] = []
                for item in items:
                    rows.append((
                        item.get("name", ""),
                        item.get("date", ""),
                        item.get("sector_type", "industry"),
                        item.get("symbol"),
                        item.get("change_pct"),
                        item.get("turnover_rate"),
                        item.get("change_pct_5d"),
                        item.get("change_pct_20d"),
                        item.get("lead_stock"),
                        item.get("main_net_inflow"),
                        item.get("main_net_inflow_5d"),
                        item.get("up_down_ratio"),
                        item.get("rank"),
                        item.get("zxj"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    ))
                payload = {
                    "symbol": "sector",
                    "rows": rows,
                    "raw_packets": [
                        (source, json.dumps(items, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_sector_quotes(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return items
            except Exception as e:
                logger.warning("Provider {} 采集热门板块失败: {}", provider.name, e)
                continue
        return None

    @_with_run_log("etf_financial_refresh")
    async def collect_etf_financial(self, symbol: str) -> dict | None:
        """采集 ETF 资产配置并落库。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                data = await provider.etf_financial(symbol)
                if not data or not data.get("date"):
                    return None
                collected_at = self._now_iso()
                source = provider.name
                row = (
                    symbol,
                    data.get("date"),
                    data.get("total_assets"),
                    data.get("stock_ratio"),
                    data.get("bond_ratio"),
                    data.get("commodity_ratio"),
                    data.get("fund_ratio"),
                    data.get("key_asset_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                payload = {
                    "symbol": symbol,
                    "row": row,
                    "raw_packets": [
                        (source, json.dumps(data, ensure_ascii=False, default=str), collected_at)
                    ],
                }
                from backend.storage.database import get_connection_sync
                with _WRITE_LOCK:
                    conn = get_connection_sync()
                    try:
                        self._insert_etf_financial(conn, payload)
                        conn.commit()
                    finally:
                        conn.close()
                return data
            except Exception as e:
                logger.warning("Provider {} 采集 ETF 资产配置失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    def get_dividends(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询分红记录，按 ex_date 降序。

        Args:
            symbol: 标的代码。
            limit: 返回行数上限。
            source: 可选数据源过滤；None 时返回所有数据源。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM dividends WHERE {where} ORDER BY ex_date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_shareholders(
        self,
        symbol: str,
        limit: int = 10,
        source: str | None = None,
    ) -> dict:
        """查询股东结构 + 股东户数历史。

        Args:
            symbol: 标的代码。
            limit: top_shareholders 返回行数上限。
            source: 可选数据源过滤。

        Returns:
            dict 含 top_shareholders / holder_count_history 两条列表。
        """
        top_conditions: list[str] = ["symbol = ?"]
        top_params: list[Any] = [symbol]
        if source is not None:
            top_conditions.append("source = ?")
            top_params.append(source)
        top_where = " AND ".join(top_conditions)
        top_params.append(limit)
        top_sql = (
            f"SELECT * FROM shareholders WHERE {top_where} "
            f"ORDER BY report_period DESC, rank ASC LIMIT ?"
        )

        cnt_conditions: list[str] = ["symbol = ?"]
        cnt_params: list[Any] = [symbol]
        if source is not None:
            cnt_conditions.append("source = ?")
            cnt_params.append(source)
        cnt_where = " AND ".join(cnt_conditions)
        cnt_sql = (
            f"SELECT * FROM shareholder_count_history WHERE {cnt_where} "
            f"ORDER BY report_date DESC"
        )

        with get_db() as conn:
            top_rows = conn.execute(top_sql, top_params).fetchall()
            cnt_rows = conn.execute(cnt_sql, cnt_params).fetchall()
        return {
            "top_shareholders": [dict(r) for r in top_rows],
            "holder_count_history": [dict(r) for r in cnt_rows],
        }

    def get_profit_forecasts(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询业绩预告，按 report_period 降序。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM profit_forecasts WHERE {where} ORDER BY report_period DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_basic(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 基本信息（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM etf_basic WHERE {where} ORDER BY date DESC LIMIT 1"
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_etf_holdings(
        self,
        symbol: str,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        """查询 ETF 成分股（最新清单）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM etf_holdings WHERE {where} ORDER BY date DESC, ratio DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_nav(
        self,
        symbol: str,
        limit: int = 60,
        source: str | None = None,
    ) -> list[dict]:
        """查询 ETF 历史净值。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM etf_nav_history WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_holders(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 持有人结构（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM etf_holders WHERE {where} ORDER BY report_date DESC LIMIT 1"
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_chip_distribution(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询筹码成本，按 date 降序。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM chip_distribution WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_margintrade(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询融资融券。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM margintrade_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_blocktrade(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询大宗交易。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM blocktrade_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_lhb(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询龙虎榜。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM lhb_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_ipo_exdiv_calendar(
        self,
        event_type: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询 ipo/exdiv 日历。

        Args:
            event_type: ipo | exdiv，None 时返回所有
            market: hk | us，None 时返回所有
            symbol: 过滤特定 symbol
            limit: 返回行数上限
        """
        conditions: list[str] = []
        params: list[Any] = []
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if market is not None:
            conditions.append("market = ?")
            params.append(market)
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        sql = f"SELECT * FROM ipo_exdiv_calendar WHERE {where} ORDER BY event_date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_us_financials(
        self,
        symbol: str,
        period_type: str | None = None,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询港美股财务，按 end_date 降序。

        Args:
            symbol: 港美股代码（usAAPL / hk00700）。
            period_type: annual | quarter，None 时返回所有。
            limit: 返回行数上限。
            source: 数据源过滤。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if period_type is not None:
            conditions.append("period_type = ?")
            params.append(period_type)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM us_financials WHERE {where} ORDER BY end_date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_sector_quotes(
        self,
        sector_type: str | None = None,
        date: str | None = None,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        """查询板块行情。

        Args:
            sector_type: industry | concept | fund_flow，None 时返回所有类型
            date: YYYY-MM-DD，None 时取最新一天
            limit: 返回行数上限
            source: 数据源过滤
        """
        conditions: list[str] = []
        params: list[Any] = []
        if sector_type is not None:
            conditions.append("sector_type = ?")
            params.append(sector_type)
        if date is not None:
            conditions.append("date = ?")
            params.append(date)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions) if conditions else "1=1"
        # 取最新日期作为子查询锚点
        if date is None:
            sql = f"""
                SELECT * FROM sector_daily_quote
                WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
                  AND {where}
                ORDER BY change_pct DESC
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT * FROM sector_daily_quote
                WHERE {where}
                ORDER BY change_pct DESC
                LIMIT ?
            """
        params.append(limit)
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_financial(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 资产配置（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM etf_financial WHERE {where} ORDER BY date DESC LIMIT 1"
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_minute_klines(
        self,
        symbol: str,
        limit: int = 240,
        from_dt: str | None = None,
        to_dt: str | None = None,
    ) -> list[dict]:
        """查询分时 K 线，按 time 降序。

        Args:
            symbol: 标的代码。
            limit: 返回行数上限（默认 240，对应 4 小时交易时间 1 分钟 K）。
            from_dt: 起始时间（ISO 字符串，可选）。
            to_dt: 截止时间（ISO 字符串，可选）。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_dt is not None:
            conditions.append("time >= ?")
            params.append(from_dt)
        if to_dt is not None:
            conditions.append("time <= ?")
            params.append(to_dt)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM minute_klines WHERE {where} ORDER BY time DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]