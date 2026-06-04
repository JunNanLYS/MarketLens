import asyncio
import sqlite3
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
_WRITE_LOCK: asyncio.Lock | None = None


def _get_write_lock() -> asyncio.Lock:
    """懒加载全局写入锁。"""
    global _WRITE_LOCK
    if _WRITE_LOCK is None:
        _WRITE_LOCK = asyncio.Lock()
    return _WRITE_LOCK


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
        self, write_lock: asyncio.Lock, symbol: str
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
                async with write_lock:
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
        write_lock = _get_write_lock()
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
        write_lock = _get_write_lock()
        return await self._collect_quote_for_symbol(write_lock, symbol)

    async def collect_daily_close(self) -> dict:
        """并发采集所有启用标的的日终四类数据。

        同一标的的 4 个数据源并行；不同标的间用 Semaphore(10) 限制并发。
        """
        started_at = self._now_iso()
        assets = self._asset_service.get_active_assets()
        summary: dict[str, dict[str, int]] = {
            "kline": {"success": 0, "failed": 0},
            "finance": {"success": 0, "failed": 0},
            "fund_flow": {"success": 0, "failed": 0},
            "technical": {"success": 0, "failed": 0},
        }
        all_errors: list[str] = []
        write_lock = _get_write_lock()
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

    async def _collect_kline(self, conn: sqlite3.Connection, symbol: str) -> dict:
        success = 0
        failed = 0
        for provider in self._get_structured_providers():
            try:
                items = await provider.kline(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_json = json.dumps(items, ensure_ascii=False, default=str)
                self._save_raw_data(conn, symbol, source, "kline", raw_json, collected_at)
                for item in items:
                    conn.execute(
                        """INSERT OR IGNORE INTO kline_daily
                           (symbol, date, open, high, low, close, volume, change_pct, source, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
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
                        ),
                    )
                success += len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集K线失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed}

    async def _collect_finance(self, conn: sqlite3.Connection, symbol: str) -> dict:
        success = 0
        failed = 0
        for provider in self._get_structured_providers():
            try:
                data = await provider.finance(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_json = json.dumps(data, ensure_ascii=False, default=str)
                self._save_raw_data(conn, symbol, source, "finance", raw_json, collected_at)
                report_period = data.get("report_period") or data.get("period") or data.get("report_date")
                conn.execute(
                    """INSERT OR IGNORE INTO financial_reports
                       (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
                        eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
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
                    ),
                )
                success += 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集财务数据失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed}

    async def _collect_fund_flow(self, conn: sqlite3.Connection, symbol: str) -> dict:
        success = 0
        failed = 0
        for provider in self._get_structured_providers():
            try:
                data = await provider.fund_flow(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_json = json.dumps(data, ensure_ascii=False, default=str)
                self._save_raw_data(conn, symbol, source, "fund_flow", raw_json, collected_at)
                # fund_flow() ?? dict?Provider ??????????
                item = data
                conn.execute(
                    """INSERT OR IGNORE INTO fund_flows
                       (symbol, date, main_net_inflow, super_large_net_inflow, large_net_inflow,
                        medium_net_inflow, small_net_inflow, net_inflow_ratio, source, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
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
                    ),
                )
                success += 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集资金流向失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed}

    async def _collect_technical(self, conn: sqlite3.Connection, symbol: str) -> dict:
        success = 0
        failed = 0
        for provider in self._get_structured_providers():
            try:
                data = await provider.technical(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_json = json.dumps(data, ensure_ascii=False, default=str)
                self._save_raw_data(conn, symbol, source, "technical", raw_json, collected_at)
                conn.execute(
                    """INSERT OR IGNORE INTO technical_indicators
                       (symbol, date, ma5, ma10, ma20, ma60,
                        macd_dif, macd_dea, macd_histogram,
                        rsi6, rsi14, boll_upper, boll_middle, boll_lower,
                        volume_ma5, volume_ma20, source, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
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
                    ),
                )
                success += 1
                break
            except Exception as e:
                logger.warning("Provider {} 采集技术指标失败: {} - {}", provider.name, symbol, e)
                failed += 1
                continue
        return {"success": success, "failed": failed}

    async def _collect_daily_close_for_symbol(
        self, write_lock: asyncio.Lock, symbol: str
    ) -> dict:
        """采集单标的的 K线/财务/资金流向/技术指标。

        同一标的的 4 个数据源相互独立，可并行；不同标的间用 Semaphore 限制并发数。
        写入侧用 write_lock 串行化。
        """
        results: dict[str, dict] = {
            "kline": {"success": 0, "failed": 0},
            "finance": {"success": 0, "failed": 0},
            "fund_flow": {"success": 0, "failed": 0},
            "technical": {"success": 0, "failed": 0},
        }
        errors: list[str] = []

        async def _run_with_lock(name: str, fn) -> None:
            try:
                async with write_lock:
                    from backend.storage.database import get_connection_sync
                    conn = get_connection_sync()
                    try:
                        result = await fn(conn, symbol)
                        results[name]["success"] += result["success"]
                        results[name]["failed"] += result["failed"]
                        conn.commit()
                    finally:
                        conn.close()
            except Exception as e:
                logger.warning("采集 {} 失败: {} - {}", name, symbol, e)
                results[name]["failed"] += 1
                errors.append(f"{symbol}/{name}: {e}")

        await asyncio.gather(
            _run_with_lock("kline", self._collect_kline),
            _run_with_lock("finance", self._collect_finance),
            _run_with_lock("fund_flow", self._collect_fund_flow),
            _run_with_lock("technical", self._collect_technical),
        )
        return {"summary": results, "errors": errors}


    async def collect_intraday(self, symbol: str, days: int = 1) -> list[dict] | None:
        """实时采集分时数据。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.minute(symbol, days=days)
                if items:
                    return items
            except Exception as e:
                logger.warning("Provider {} 采集分时失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_shareholder(self, symbol: str) -> dict | None:
        """实时采集股东结构数据。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                result = await provider.shareholder(symbol)
                if result:
                    return result
            except Exception as e:
                logger.warning("Provider {} 采集股东结构失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_reserve(self, symbol: str) -> dict | None:
        """实时采集业绩预告。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                result = await provider.reserve(symbol)
                if result:
                    return result
            except Exception as e:
                logger.warning("Provider {} 采集业绩预告失败: {} - {}", provider.name, symbol, e)
                continue
        return None

    async def collect_dividend(self, symbol: str) -> list[dict] | None:
        """实时采集分红记录。"""
        for provider in self._get_structured_providers():
            if not isinstance(provider, WeStockProvider):
                continue
            try:
                items = await provider.dividend(symbol)
                if items:
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