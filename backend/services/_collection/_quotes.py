"""Quote collection mixin for CollectionService."""
import asyncio
import json
import threading

from loguru import logger

from backend.services._collection._core import _WRITE_LOCK
from backend.services._collection._helpers import _save_raw_data
from backend.storage.database import get_db, get_connection_sync


class _CollectionQuotesMixin:
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
                    conn = get_connection_sync()
                    try:
                        _save_raw_data(
                            conn, symbol, source, "quote", raw_json, collected_at
                        )
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
                logger.warning(
                    "Provider {} 采集行情失败: {} - {}", provider.name, symbol, e
                )
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
            self._write_run_log(
                conn, "quote", status, started_at, finished_at, error_message, total
            )

        return {"success": success, "failed": failed, "total": total}

    async def collect_quote_single(self, symbol: str) -> dict | None:
        write_lock = _WRITE_LOCK
        return await self._collect_quote_for_symbol(write_lock, symbol)
