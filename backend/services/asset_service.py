import re
import sqlite3
import threading
from typing import Any

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.config import get_config
from backend.storage.database import get_db
from backend.utils import build_fund_flow_summary, escape_like

SYMBOL_PATTERN = re.compile(r"^(sh|sz|hk|us|fut|hf|nf)(\w+)$")

# CLAUDE.md 硬约束：所有 SQLite 写路径必须持写锁串行化
_WRITE_LOCK: threading.Lock = threading.Lock()


class AssetExistsError(ValueError):
    """重复添加标的时抛出的异常，附带已存在标的快照供上层展示。"""

    def __init__(self, message: str, existing_asset: dict[str, Any]) -> None:
        super().__init__(message)
        self.existing_asset = existing_asset


class AssetService:
    """标的管理服务，提供追踪标的 CRUD 功能。"""

    def __init__(self, providers: dict[str, list[BaseProvider]] | None = None) -> None:
        if providers is not None:
            self._providers = providers
        else:
            config = get_config()
            self._providers = create_providers(config)

    def _get_structured_providers(self) -> list[BaseProvider]:
        return self._providers.get("structured", [])

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str] | None:
        match = SYMBOL_PATTERN.match(symbol)
        if not match:
            return None
        prefix = match.group(1)
        code = match.group(2)
        return prefix, code

    @staticmethod
    def _infer_market(symbol: str) -> str | None:
        parsed = AssetService._parse_symbol(symbol)
        if parsed is None:
            return None
        return parsed[0]

    @staticmethod
    def _tags_to_str(tags: list[str] | str | None) -> str | None:
        if tags is None:
            return None
        if isinstance(tags, list):
            return ",".join(tags)
        return tags

    @staticmethod
    def _tags_to_list(tags: str | None) -> list[str]:
        if not tags:
            return []
        return [t.strip() for t in tags.split(",") if t.strip()]

    @staticmethod
    def _row_to_dict(row: dict) -> dict:
        result = dict(row)
        if "tags" in result and result["tags"] is not None:
            result["tags"] = AssetService._tags_to_list(result["tags"])
        return result

    async def add_asset(self, data: dict) -> dict:
        raw_symbol: str = data.get("symbol", "").strip()
        if not raw_symbol:
            raise ValueError("symbol 不能为空")

        # 如果 symbol 不带市场前缀但传入了 market，自动拼接前缀
        # （前端表单 symbol 和 market 是分开填的，用户可能只填 `300750` + 选 `sz`）
        supplied_market = data.get("market") or ""
        if self._parse_symbol(raw_symbol) is None and supplied_market in ("sh", "sz", "hk", "us", "fut", "hf", "nf"):
            raw_symbol = f"{supplied_market}{raw_symbol}"

        parsed = self._parse_symbol(raw_symbol)
        if parsed is None:
            raise ValueError(f"无法识别代码 '{raw_symbol}'，请使用带市场前缀的格式（如 sz300750、sh600519）")

        prefix, code = parsed
        symbol = f"{prefix}{code}"

        # symbol 前缀是 market 的权威来源；前端传入的 market 仅在 symbol 不带前缀时用于拼接
        market = self._infer_market(symbol) or data.get("market")
        if market is None:
            raise ValueError(f"无法识别代码 '{symbol}'")

        name = data.get("name", "").strip() or None
        if not name:
            name = await self._try_search_name(symbol)

        asset_type = data.get("asset_type", "stock") or "stock"
        tags = self._tags_to_str(data.get("tags"))
        notes = data.get("notes")

        with _WRITE_LOCK, get_db() as conn:
            existing = conn.execute(
                """SELECT id, symbol, name, market, asset_type, enabled
                   FROM tracked_assets WHERE symbol = ?""",
                (symbol,),
            ).fetchone()
            if existing is not None:
                # 软删除记录：重新启用并更新字段
                if not existing["enabled"]:
                    conn.execute(
                        """UPDATE tracked_assets
                           SET enabled = 1, name = ?, asset_type = ?, tags = ?, notes = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (name, asset_type, tags, notes, existing["id"]),
                    )
                    row = conn.execute(
                        "SELECT * FROM tracked_assets WHERE id = ?",
                        (existing["id"],),
                    ).fetchone()
                    logger.info("已重新启用标的: {} ({})", symbol, name)
                    return self._row_to_dict(dict(row))

                raise AssetExistsError(
                    f"标的 '{symbol}' 已在追踪列表中（ID: {existing['id']}）",
                    {
                        "id": existing["id"],
                        "symbol": existing["symbol"],
                        "name": existing["name"],
                        "market": existing["market"],
                        "asset_type": existing["asset_type"],
                        "enabled": bool(existing["enabled"]),
                    },
                )

            try:
                cursor = conn.execute(
                    """INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled, tags, notes)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (symbol, name, market, asset_type, tags, notes),
                )
            except sqlite3.IntegrityError:
                fallback = conn.execute(
                    """SELECT id, symbol, name, market, asset_type, enabled
                       FROM tracked_assets WHERE symbol = ?""",
                    (symbol,),
                ).fetchone()
                if fallback is None:
                    raise ValueError(f"标的 '{symbol}' 已在追踪列表中") from None
                raise AssetExistsError(
                    f"标的 '{symbol}' 已在追踪列表中（ID: {fallback['id']}）",
                    {
                        "id": fallback["id"],
                        "symbol": fallback["symbol"],
                        "name": fallback["name"],
                        "market": fallback["market"],
                        "asset_type": fallback["asset_type"],
                        "enabled": bool(fallback["enabled"]),
                    },
                ) from None

            asset_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
            ).fetchone()

        logger.info("已添加追踪标的: {} ({})", symbol, name)
        return self._row_to_dict(dict(row))

    async def _try_search_name(self, symbol: str) -> str:
        for provider in self._get_structured_providers():
            try:
                results = await provider.search(symbol)
                if results:
                    for item in results:
                        if item.get("symbol", "").lower() == symbol:
                            return item.get("name", symbol)
                    return results[0].get("name", symbol)
            except Exception:
                logger.warning("Provider {} 搜索失败，跳过", provider.name)
                continue
        return symbol

    def get_assets(
        self,
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        conditions: list[str] = []
        params: list[Any] = []

        effective_filters = dict(filters) if filters else {}
        if "enabled" not in effective_filters:
            conditions.append("ta.enabled = 1")
        else:
            conditions.append("ta.enabled = ?")
            params.append(1 if effective_filters["enabled"] else 0)

        if "market" in effective_filters:
            conditions.append("ta.market = ?")
            params.append(effective_filters["market"])

        if "asset_type" in effective_filters:
            conditions.append("ta.asset_type = ?")
            params.append(effective_filters["asset_type"])

        if "tag" in effective_filters:
            conditions.append("ta.tags LIKE ? ESCAPE '\\'")
            params.append(f"%{escape_like(effective_filters['tag'])}%")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        # 使用 CTE + ROW_NUMBER() 取每条标的的最新行情，避免 LEFT JOIN 子查询对每行执行一次。
        # market_quotes 1 个标的/15min 频率下全年 ~3.5M 行；CTE 限定 collected_at > 1 day 窗口，
        # 配合已有 idx_market_quotes_symbol_collected(symbol, collected_at DESC) 索引
        # 走 loose-index-scan，把 CTE 物化行数从全表量级降到 1 天 ~10K 量级。
        count_sql = f"SELECT COUNT(*) FROM tracked_assets ta {where_clause}"
        data_sql = f"""
            WITH latest_quotes AS (
                SELECT symbol, price, change_pct, collected_at,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY collected_at DESC) AS rn
                FROM market_quotes
                WHERE collected_at > datetime('now', '-1 day')
            )
            SELECT ta.*,
                   lq.price AS latest_price,
                   lq.change_pct AS latest_change_pct,
                   lq.collected_at AS latest_quote_at
            FROM tracked_assets ta
            LEFT JOIN latest_quotes lq ON lq.symbol = ta.symbol AND lq.rn = 1
            {where_clause}
            ORDER BY ta.created_at DESC
            LIMIT ? OFFSET ?
        """

        with get_db() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
            rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        items = [self._row_to_dict(dict(row)) for row in rows]
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "items": items,
            "page_info": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    def get_asset_by_id(self, asset_id: int) -> dict | None:
        """获取标的详情（合并 6 条独立 SELECT 为 2 条 CTE 查询）。"""
        with get_db() as conn:
            # CTE 1: 标的 + 行情 + 财务 + 报告（4 张表通过 LEFT JOIN + 窗口函数取最新）
            row = conn.execute(
                """
                WITH
                latest_quote AS (
                    SELECT symbol, price, change, change_pct, open, high, low,
                           prev_close, volume, amount, collected_at,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY collected_at DESC) AS rn
                    FROM market_quotes
                ),
                latest_finance AS (
                    SELECT symbol, report_period, revenue_yoy, eps, roe,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY collected_at DESC) AS rn
                    FROM financial_reports
                ),
                latest_report AS (
                    SELECT symbol, action, confidence, generated_at,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY generated_at DESC) AS rn
                    FROM ai_reports
                )
                SELECT ta.*,
                       lq.price AS q_price, lq.change AS q_change, lq.change_pct AS q_change_pct,
                       lq.open AS q_open, lq.high AS q_high, lq.low AS q_low,
                       lq.prev_close AS q_prev_close, lq.volume AS q_volume,
                       lq.amount AS q_amount, lq.collected_at AS q_collected_at,
                       lf.report_period AS f_report_period, lf.revenue_yoy AS f_revenue_yoy,
                       lf.eps AS f_eps, lf.roe AS f_roe,
                       lr.action AS r_action, lr.confidence AS r_confidence,
                       lr.generated_at AS r_generated_at
                FROM tracked_assets ta
                LEFT JOIN latest_quote lq ON lq.symbol = ta.symbol AND lq.rn = 1
                LEFT JOIN latest_finance lf ON lf.symbol = ta.symbol AND lf.rn = 1
                LEFT JOIN latest_report lr ON lr.symbol = ta.symbol AND lr.rn = 1
                WHERE ta.id = ?
                """,
                (asset_id,),
            ).fetchone()
            if row is None:
                return None

            result = self._row_to_dict(dict(row))

            # 把 joined 字段映射到原有 schema
            if row["q_price"] is not None or row["q_collected_at"] is not None:
                result["quote"] = {
                    "price": row["q_price"],
                    "change": row["q_change"],
                    "change_pct": row["q_change_pct"],
                    "open": row["q_open"],
                    "high": row["q_high"],
                    "low": row["q_low"],
                    "prev_close": row["q_prev_close"],
                    "volume": row["q_volume"],
                    "amount": row["q_amount"],
                    "collected_at": row["q_collected_at"],
                }
            else:
                result["quote"] = None
            if row["f_report_period"] is not None:
                result["finance_summary"] = {
                    "report_period": row["f_report_period"],
                    "revenue_yoy": row["f_revenue_yoy"],
                    "eps": row["f_eps"],
                    "roe": row["f_roe"],
                }
            else:
                result["finance_summary"] = None
            if row["r_action"] is not None:
                result["latest_report"] = {
                    "action": row["r_action"],
                    "confidence": row["r_confidence"],
                    "generated_at": row["r_generated_at"],
                }
            else:
                result["latest_report"] = None

            # CTE 2: K线 + 资金流向（另一条独立查询，2 张表无强关联，分开更清晰）
            kline_flow_rows = conn.execute(
                """
                WITH
                klines AS (
                    SELECT symbol, close, date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM kline_daily
                ),
                flows AS (
                    SELECT symbol, date, main_net_inflow, net_inflow_ratio,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM fund_flows
                )
                SELECT k.symbol AS k_symbol, k.close AS k_close, k.date AS k_date,
                       f.symbol AS f_symbol, f.date AS f_date,
                       f.main_net_inflow AS f_main_net_inflow, f.net_inflow_ratio AS f_net_inflow_ratio
                FROM tracked_assets ta
                LEFT JOIN klines k ON k.symbol = ta.symbol AND k.rn <= 60
                LEFT JOIN flows f ON f.symbol = ta.symbol AND f.rn <= 5
                WHERE ta.id = ?
                ORDER BY k.date DESC, f.date DESC
                """,
                (asset_id,),
            ).fetchall()

            kline_rows: list[dict] = []
            fund_rows: list[dict] = []
            for r in kline_flow_rows:
                d = dict(r)
                if d["k_close"] is not None and d["k_date"] is not None:
                    kline_rows.append({"close": d["k_close"], "date": d["k_date"]})
                if d["f_main_net_inflow"] is not None and d["f_date"] is not None:
                    fund_rows.append(
                        {
                            "date": d["f_date"],
                            "main_net_inflow": d["f_main_net_inflow"],
                            "net_inflow_ratio": d["f_net_inflow_ratio"],
                        }
                    )

            result["kline_summary"] = self._build_kline_summary(kline_rows)
            result["fund_flow_summary"] = build_fund_flow_summary(fund_rows)

            # latest_report 字段截断 bug 修复：CTE 内只取 action/confidence/generated_at，
            # 导致详情页 AI 报告 tab 的 risk_level/summary/bullish_reasons/bearish_reasons/key_risks/data_used 全为空。
            # 改用 ReportService.get_latest_report(symbol) 作为单一数据源（含全字段）。
            from backend.services.report_service import ReportService

            symbol: str = result.get("symbol", "")
            if symbol:
                result["latest_report"] = ReportService.get_latest_report(symbol)

        return result

    @staticmethod
    def _build_kline_summary(kline_rows: list[dict]) -> dict | None:
        """构建 K 线摘要。

        若上游（EvidenceBuilder）已计算 ma5/ma20/ma60 字段，直接复用；否则
        使用滑动窗口 O(n) 计算，避免每次重新切片求和。
        """
        if not kline_rows:
            return None

        # 数据按时间升序（与 EvidenceBuilder 一致）
        ordered = [row for row in reversed(kline_rows) if row.get("close") is not None]
        if not ordered:
            return None

        latest = ordered[-1]
        latest_close = latest["close"]

        # 优先使用上游已计算的 ma 字段
        ma5 = latest.get("ma5")
        ma20 = latest.get("ma20")
        ma60 = latest.get("ma60")

        if ma5 is None or ma20 is None or ma60 is None:
            closes = [row["close"] for row in ordered]
            # 滑动窗口 O(n) 计算
            windows = (5, 20, 60)
            running_sums: dict[int, float] = {w: 0.0 for w in windows}
            values: dict[int, float | None] = {w: None for w in windows}
            for i, c in enumerate(closes):
                for w in windows:
                    running_sums[w] += c
                    if i >= w:
                        running_sums[w] -= closes[i - w]
                    if i >= w - 1:
                        values[w] = round(running_sums[w] / w, 4)
            ma5 = values[5] if ma5 is None else ma5
            ma20 = values[20] if ma20 is None else ma20
            ma60 = values[60] if ma60 is None else ma60

        trend = "数据不足"
        if ma5 is not None and ma20 is not None and ma60 is not None:
            if ma5 > ma20 > ma60:
                trend = "MA5 > MA20 > MA60 多头排列"
            elif ma5 < ma20 < ma60:
                trend = "MA5 < MA20 < MA60 空头排列"
            elif ma5 > ma20:
                trend = "MA5 > MA20 短期偏多"
            elif ma5 < ma20:
                trend = "MA5 < MA20 短期偏空"
            else:
                trend = "MA5 ≈ MA20 横盘整理"

        summary: dict[str, Any] = {
            "latest_close": latest_close,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "trend": trend,
        }
        return summary

    def update_asset(self, asset_id: int, data: dict) -> dict | None:
        updates: dict[str, Any] = {}

        if "enabled" in data:
            updates["enabled"] = 1 if data["enabled"] else 0

        if "tags" in data:
            updates["tags"] = self._tags_to_str(data["tags"])

        if "notes" in data:
            updates["notes"] = data["notes"]

        if not updates:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
                ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(dict(row))

        updates["updated_at"] = "CURRENT_TIMESTAMP"

        set_parts: list[str] = []
        values: list[Any] = []
        for k, v in updates.items():
            if k == "updated_at":
                set_parts.append(f"{k} = CURRENT_TIMESTAMP")
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)

        set_clause = ", ".join(set_parts)
        sql = f"UPDATE tracked_assets SET {set_clause} WHERE id = ?"

        with _WRITE_LOCK, get_db() as conn:
            cursor = conn.execute(sql, values + [asset_id])
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
            ).fetchone()

        logger.info("已更新标的 ID={}", asset_id)
        return self._row_to_dict(dict(row))

    def delete_asset(self, asset_id: int, soft: bool = True) -> bool:
        with _WRITE_LOCK, get_db() as conn:
            if soft:
                cursor = conn.execute(
                    "UPDATE tracked_assets SET enabled = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND enabled = 1",
                    (asset_id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM tracked_assets WHERE id = ?", (asset_id,)
                )
            affected = cursor.rowcount > 0

        if affected:
            action = "停用" if soft else "物理删除"
            logger.info("已{}标的 ID={}", action, asset_id)
        return affected

    async def search_assets(
        self, keyword: str, market: str | None = None, include_local: bool = True
    ) -> list[dict]:
        """搜索标的：先调所有 structured Provider（外部数据源），再回退查本地 tracked_assets。

        每条结果附 source（provider.name / "local"）和 already_tracked 标志，
        供前端区分已添加/未添加、来源，避免重复追踪。
        """
        results: list[dict] = []
        seen_symbols: set[str] = set()

        for provider in self._get_structured_providers():
            try:
                items = await provider.search(keyword)
                for item in items:
                    sym = item.get("symbol", "")
                    if sym and sym not in seen_symbols:
                        if market is None or item.get("market") == market:
                            item["source"] = provider.name
                            item["already_tracked"] = self._is_tracked(sym)
                            results.append(item)
                            seen_symbols.add(sym)
            except Exception:
                logger.warning("Provider {} 搜索失败，跳过", provider.name)
                continue

        # 本地回退：外部结果不足时查已追踪的标的，让用户能搜到本地存在的资产
        if include_local and len(results) < 10:
            for item in self._search_local(keyword, market):
                sym = item.get("symbol", "")
                if sym and sym not in seen_symbols:
                    item["source"] = "local"
                    item["already_tracked"] = True
                    results.append(item)
                    seen_symbols.add(sym)

        return results

    def _is_tracked(self, symbol: str) -> bool:
        """检查标的 symbol 是否已在本地追踪列表中。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM tracked_assets WHERE symbol = ? LIMIT 1", (symbol,)
            ).fetchone()
        return row is not None

    def _search_local(self, keyword: str, market: str | None) -> list[dict]:
        """在 tracked_assets 里按 symbol 或 name 模糊匹配。"""
        kw = escape_like(keyword)
        conditions = ["(symbol LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\')"]
        params: list[Any] = [f"%{kw}%", f"%{kw}%"]
        if market is not None:
            conditions.append("market = ?")
            params.append(market)
        sql = (
            "SELECT symbol, name, market, asset_type FROM tracked_assets "
            f"WHERE {' AND '.join(conditions)} LIMIT 10"
        )
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"symbol": r[0], "name": r[1], "market": r[2], "asset_type": r[3]}
            for r in rows
        ]

    def get_active_assets(self) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tracked_assets WHERE enabled = 1 ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(dict(row)) for row in rows]
