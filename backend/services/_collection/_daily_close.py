"""Daily close collection mixin for CollectionService."""
import asyncio
import json
import sqlite3
import threading

from loguru import logger

from backend.services._collection._core import _WRITE_LOCK
from backend.services._collection._helpers import _save_raw_data
from backend.storage.database import get_db, get_connection_sync


# 日终 7 类数据 INSERT OR IGNORE 模板（含表名 + 列名 + 占位符）。
# 用 dict 而非函数对象保留原 7 个 _insert_* 的"零参数差异"语义。
DAILY_CLOSE_INSERT_SQL: dict[str, str] = {
    "kline": """INSERT OR IGNORE INTO kline_daily
       (symbol, date, open, high, low, close, volume, change_pct, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    "finance": """INSERT OR IGNORE INTO financial_reports
       (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
        eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    "fund_flow": """INSERT OR IGNORE INTO fund_flows
       (symbol, date, main_net_inflow, super_large_net_inflow, large_net_inflow,
        medium_net_inflow, small_net_inflow, net_inflow_ratio, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    "technical": """INSERT OR IGNORE INTO technical_indicators
       (symbol, date, ma5, ma10, ma20, ma60,
        macd_dif, macd_dea, macd_histogram,
        rsi6, rsi14, boll_upper, boll_middle, boll_lower,
        volume_ma5, volume_ma20, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    "dividend": """INSERT OR IGNORE INTO dividends
       (symbol, ex_date, cash_dividend, share_bonus,
        record_date, announce_date, dividend_year, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    "reserve": """INSERT OR IGNORE INTO profit_forecasts
       (symbol, report_period, forecast_type, profit_lower, profit_upper,
        change_lower, change_upper, summary, source, collected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
}

# 每类数据在 raw_data.data_type 列中的标识。
DAILY_CLOSE_DATA_TYPES: dict[str, str] = {
    "kline": "kline",
    "finance": "finance",
    "fund_flow": "fund_flow",
    "technical": "technical",
    "dividend": "dividend",
    "shareholder": "shareholder",
    "reserve": "reserve",
}


def _dividend_year_normalize(value) -> int | None:
    """dividend_year 字段归一化：westock 输 "2023" 时转 int，缺值/非法转 None。"""
    if isinstance(value, int):
        return value
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except (ValueError, TypeError):
        return None


class _CollectionDailyCloseMixin:
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
            self._write_run_log(
                conn,
                "daily_close",
                status,
                started_at,
                finished_at,
                error_message,
                affected,
            )

        return summary

    async def _fetch_and_build(
        self,
        symbol: str,
        provider_method_name: str,
        row_builder,
        error_label: str,
        needs_data_get: bool = False,
    ) -> dict:
        """泛型 fetch：遍历 provider → 调 method → row_builder 构建 row → 返回 payload。

        与 _run_collect_with_lock 的区别：此方法不持写锁、不落库；只 fetch
        （并发无锁网络 IO），与 commit 阶段解耦。

        Args:
            symbol: 标的代码。
            provider_method_name: provider 方法名（如 "kline" / "finance"）。
            row_builder: 闭包 (item/data, source, collected_at) -> tuple | list[tuple]；
                接收 provider 返回的原始 item/data，返回单条 row 或多条 row 列表。
            error_label: 异常日志里的中文名（如 "K线"）。
            needs_data_get: True 时把 provider 返回当 dict 用（finance/fund_flow/...）；
                False 时当 list 迭代（kline/dividend/...）。

        Returns:
            {"success": int, "failed": int, "rows" | "row" | "top_rows" | ...,
             "raw_packets": list[tuple]}
        """
        success = 0
        failed = 0
        rows: list[tuple] = []
        row: tuple | None = None
        top_rows: list[tuple] = []
        count_rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            try:
                method = getattr(provider, provider_method_name)
                data = await method(symbol)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                built = row_builder(data, source, collected_at)
                if isinstance(built, tuple):
                    row = built
                    success = 1
                elif isinstance(built, list):
                    rows = built
                    success = len(built)
                else:
                    # row_builder 可选择返回 dict 含 "top_rows"/"count_rows"
                    top_rows = built.get("top_rows", [])
                    count_rows = built.get("count_rows", [])
                    success = len(top_rows) + len(count_rows)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集{}失败: {} - {}",
                    provider.name,
                    error_label,
                    symbol,
                    e,
                )
                failed += 1
                continue
        result = {
            "success": success,
            "failed": failed,
            "raw_packets": raw_packets,
            "top_rows": top_rows,
            "count_rows": count_rows,
        }
        if row is not None:
            result["row"] = row
        if rows:
            result["rows"] = rows
        return result

    def _insert_daily_close(
        self,
        conn: sqlite3.Connection,
        name: str,
        payload: dict,
    ) -> None:
        """泛型日终落库：写 raw_data + 执行 INSERT OR IGNORE 模板。

        Args:
            conn: 同步 DB 连接。
            name: 数据类名（"kline"/"finance"/...），
                用于查 DAILY_CLOSE_INSERT_SQL 与 DAILY_CLOSE_DATA_TYPES。
            payload: fetch 阶段返回的 dict（含 raw_packets + row/rows/top_rows/count_rows）。
        """
        data_type = DAILY_CLOSE_DATA_TYPES[name]
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, data_type, raw_json, collected_at
            )
        sql = DAILY_CLOSE_INSERT_SQL[name]
        if "row" in payload and payload["row"] is not None:
            conn.execute(sql, payload["row"])
        elif "rows" in payload and payload["rows"]:
            conn.executemany(sql, payload["rows"])
        # shareholder 走双表，由 _insert_shareholders 单独处理

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
                self._fetch_and_build(
                    symbol,
                    "kline",
                    lambda items, src, ts: [
                        (
                            symbol,
                            it.get("date"),
                            it.get("open"),
                            it.get("high"),
                            it.get("low"),
                            it.get("close"),
                            it.get("volume"),
                            it.get("change_pct"),
                            it.get("source", src),
                            it.get("collected_at", ts),
                        )
                        for it in items
                    ],
                    "K线",
                ),
                self._fetch_and_build(
                    symbol,
                    "finance",
                    lambda data, src, ts: (
                        symbol,
                        data.get("report_period")
                        or data.get("period")
                        or data.get("report_date"),
                        data.get("revenue"),
                        data.get("revenue_yoy"),
                        data.get("net_profit"),
                        data.get("net_profit_yoy"),
                        data.get("eps"),
                        data.get("roe"),
                        data.get("debt_ratio"),
                        data.get("gross_margin"),
                        data.get("net_margin"),
                        data.get("source", src),
                        data.get("collected_at", ts),
                    ),
                    "财务数据",
                ),
                self._fetch_and_build(
                    symbol,
                    "fund_flow",
                    lambda data, src, ts: (
                        symbol,
                        data.get("date"),
                        data.get("main_net_inflow") or data.get("net_flow"),
                        data.get("super_large_net_inflow"),
                        data.get("large_net_inflow") or data.get("main_inflow"),
                        data.get("medium_net_inflow"),
                        data.get("small_net_inflow"),
                        data.get("net_inflow_ratio"),
                        data.get("source", src),
                        data.get("collected_at", ts),
                    ),
                    "资金流向",
                ),
                self._fetch_and_build(
                    symbol,
                    "technical",
                    lambda data, src, ts: (
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
                        data.get("source", src),
                        data.get("collected_at", ts),
                    ),
                    "技术指标",
                ),
                self._fetch_and_build(
                    symbol,
                    "dividend",
                    lambda items, src, ts: [
                        (
                            symbol,
                            it.get("ex_date", ""),
                            it.get("cash_dividend"),
                            it.get("share_bonus"),
                            it.get("record_date"),
                            it.get("announce_date"),
                            _dividend_year_normalize(it.get("dividend_year")),
                            it.get("source", src),
                            it.get("collected_at", ts),
                        )
                        for it in items
                    ],
                    "分红",
                ),
                self._fetch_and_build(
                    symbol,
                    "shareholder",
                    lambda data, src, ts: (
                        {
                            "top_rows": [
                                (
                                    symbol,
                                    data.get("report_period")
                                    or data.get("end_date")
                                    or ts,
                                    sh.get("rank"),
                                    sh.get("name"),
                                    sh.get("shares"),
                                    sh.get("ratio"),
                                    sh.get("change"),
                                    data.get("source", src),
                                    data.get("collected_at", ts),
                                )
                                for sh in data.get("top_shareholders", [])
                            ],
                            "count_rows": [
                                (
                                    symbol,
                                    hc.get("date", ""),
                                    hc.get("total_holders"),
                                    hc.get("avg_shares"),
                                    data.get("source", src),
                                    data.get("collected_at", ts),
                                )
                                for hc in data.get("holder_count_history", [])
                            ],
                        }
                        if data.get("top_shareholders")
                        else []
                    ),
                    "股东结构",
                ),
                self._fetch_and_build(
                    symbol,
                    "reserve",
                    lambda data, src, ts: (
                        symbol,
                        data.get("report_period"),
                        data.get("forecast_type") or "未知",
                        data.get("profit_lower"),
                        data.get("profit_upper"),
                        data.get("change_lower"),
                        data.get("change_upper"),
                        data.get("summary"),
                        data.get("source", src),
                        data.get("collected_at", ts),
                    )
                    if data and data.get("report_period")
                    else None,
                    "业绩预告",
                ),
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
        try:
            with write_lock:
                conn = get_connection_sync()
                try:
                    self._insert_daily_close(conn, "kline", {"symbol": symbol, **kline_p})
                    self._insert_daily_close(conn, "finance", {"symbol": symbol, **finance_p})
                    self._insert_daily_close(conn, "fund_flow", {"symbol": symbol, **fund_p})
                    self._insert_daily_close(conn, "technical", {"symbol": symbol, **tech_p})
                    self._insert_daily_close(conn, "dividend", {"symbol": symbol, **dividend_p})
                    self._insert_daily_close(conn, "reserve", {"symbol": symbol, **reserve_p})
                    # 股东结构走双表，保留原 _insert_shareholders
                    self._insert_shareholders(
                        conn, {"symbol": symbol, **shareholder_p}
                    )
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
