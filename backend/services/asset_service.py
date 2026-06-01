import re
from typing import Any

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.config import get_config
from backend.storage.database import get_db

SYMBOL_PATTERN = re.compile(r"^(sh|sz|hk|us|fut)(\w+)$")


def _escape_like(value: str, escape_char: str = "\\") -> str:
    return value.replace(escape_char, escape_char * 2).replace("%", f"{escape_char}%").replace("_", f"{escape_char}_")


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

    def add_asset(self, data: dict) -> dict:
        raw_symbol: str = data.get("symbol", "").strip()
        if not raw_symbol:
            raise ValueError("symbol 不能为空")

        parsed = self._parse_symbol(raw_symbol)
        if parsed is None:
            raise ValueError(f"无法识别代码 '{raw_symbol}'")

        prefix, code = parsed
        symbol = f"{prefix}{code}"

        market = data.get("market") or self._infer_market(symbol)
        if market is None:
            raise ValueError(f"无法识别代码 '{symbol}'")

        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, symbol FROM tracked_assets WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"标的 '{symbol}' 已在追踪列表中（ID: {existing['id']}）"
                )

        name = data.get("name", "").strip() or None
        if not name:
            name = self._try_search_name(symbol)

        asset_type = data.get("asset_type", "stock") or "stock"
        tags = self._tags_to_str(data.get("tags"))
        notes = data.get("notes")

        with get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled, tags, notes)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (symbol, name, market, asset_type, tags, notes),
            )
            asset_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
            ).fetchone()

        logger.info("已添加追踪标的: {} ({})", symbol, name)
        return self._row_to_dict(dict(row))

    def _try_search_name(self, symbol: str) -> str:
        for provider in self._get_structured_providers():
            try:
                results = provider.search(symbol)
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
            params.append(f"%{_escape_like(effective_filters['tag'])}%")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        count_sql = f"SELECT COUNT(*) FROM tracked_assets ta {where_clause}"
        data_sql = f"""
            SELECT ta.*,
                   mq.price AS latest_price,
                   mq.change_pct AS latest_change_pct,
                   mq.collected_at AS latest_quote_at
            FROM tracked_assets ta
            LEFT JOIN market_quotes mq ON mq.symbol = ta.symbol
                AND mq.collected_at = (
                    SELECT MAX(mq2.collected_at)
                    FROM market_quotes mq2
                    WHERE mq2.symbol = ta.symbol
                )
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
        with get_db() as conn:
            asset_row = conn.execute(
                "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
            ).fetchone()
            if asset_row is None:
                return None

            result = self._row_to_dict(dict(asset_row))

            quote_row = conn.execute(
                """SELECT price, change, change_pct, open, high, low, volume, collected_at
                   FROM market_quotes
                   WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT 1""",
                (result["symbol"],),
            ).fetchone()
            if quote_row is not None:
                result["quote"] = dict(quote_row)
            else:
                result["quote"] = None

            kline_rows = conn.execute(
                """SELECT close, date FROM kline_daily
                   WHERE symbol = ?
                   ORDER BY date DESC LIMIT 60""",
                (result["symbol"],),
            ).fetchall()
            result["kline_summary"] = self._build_kline_summary(kline_rows)

            finance_row = conn.execute(
                """SELECT report_period, revenue_yoy, eps, roe
                   FROM financial_reports
                   WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT 1""",
                (result["symbol"],),
            ).fetchone()
            if finance_row is not None:
                result["finance_summary"] = dict(finance_row)
            else:
                result["finance_summary"] = None

            fund_rows = conn.execute(
                """SELECT date, main_net_inflow FROM fund_flows
                   WHERE symbol = ?
                   ORDER BY date DESC LIMIT 5""",
                (result["symbol"],),
            ).fetchall()
            result["fund_flow_summary"] = self._build_fund_flow_summary(fund_rows)

            report_row = conn.execute(
                """SELECT action, confidence, generated_at
                   FROM ai_reports
                   WHERE symbol = ?
                   ORDER BY generated_at DESC LIMIT 1""",
                (result["symbol"],),
            ).fetchone()
            if report_row is not None:
                result["latest_report"] = dict(report_row)
            else:
                result["latest_report"] = None

        return result

    @staticmethod
    def _build_kline_summary(kline_rows: list[dict]) -> dict | None:
        if not kline_rows:
            return None

        closes = [row["close"] for row in reversed(kline_rows) if row["close"] is not None]
        if not closes:
            return None

        latest_close = closes[-1]
        ma5 = sum(closes[-5:]) / len(closes[-5:]) if len(closes) >= 5 else None
        ma20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else None
        ma60 = sum(closes[-60:]) / len(closes[-60:]) if len(closes) >= 60 else None

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

    @staticmethod
    def _build_fund_flow_summary(fund_rows: list[dict]) -> dict | None:
        if not fund_rows:
            return None

        net_flow_5d = sum(
            row["main_net_inflow"] for row in fund_rows if row["main_net_inflow"] is not None
        )

        inflows = [row for row in fund_rows if row["main_net_inflow"] is not None and row["main_net_inflow"] > 0]
        outflows = [row for row in fund_rows if row["main_net_inflow"] is not None and row["main_net_inflow"] < 0]

        if len(inflows) >= 3:
            trend = f"连续 {len(inflows)} 日净流入"
        elif len(outflows) >= 3:
            trend = f"连续 {len(outflows)} 日净流出"
        else:
            trend = "近 5 日资金流向交替"

        return {
            "net_flow_5d": net_flow_5d,
            "trend": trend,
        }

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

        with get_db() as conn:
            cursor = conn.execute(sql, values + [asset_id])
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM tracked_assets WHERE id = ?", (asset_id,)
            ).fetchone()

        logger.info("已更新标的 ID={}", asset_id)
        return self._row_to_dict(dict(row))

    def delete_asset(self, asset_id: int, soft: bool = True) -> bool:
        with get_db() as conn:
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

    def search_assets(
        self, keyword: str, market: str | None = None
    ) -> list[dict]:
        results: list[dict] = []
        seen_symbols: set[str] = set()

        for provider in self._get_structured_providers():
            try:
                items = provider.search(keyword)
                for item in items:
                    sym = item.get("symbol", "")
                    if sym and sym not in seen_symbols:
                        if market is None or item.get("market") == market:
                            item["source"] = provider.name
                            results.append(item)
                            seen_symbols.add(sym)
            except Exception:
                logger.warning("Provider {} 搜索失败，跳过", provider.name)
                continue

        return results

    def get_active_assets(self) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tracked_assets WHERE enabled = 1 ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(dict(row)) for row in rows]
