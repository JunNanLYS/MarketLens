"""证据构建器（异步版）——聚合各类数据为 AI 分析提供输入。"""

from backend.config import get_config
from backend.storage.database import aget_db


class EvidenceBuilder:

    @staticmethod
    def _evidence_limits() -> dict:
        """从配置文件获取证据查询的行数限制。"""
        cfg = get_config().get("evidence", {})
        return {
            "kline_limit": cfg.get("kline_limit", 60),
            "fund_flow_limit": cfg.get("fund_flow_limit", 5),
            "finance_limit": cfg.get("finance_limit", 2),
            "news_days": cfg.get("news_days", 7),
        }
    @staticmethod
    async def build(symbol: str, conn=None) -> dict:
        close_conn = conn is None
        if conn is None:
            from backend.storage.database import aget_connection
            conn = await aget_connection()

        try:
            quote = await EvidenceBuilder._build_quote(conn, symbol)
            klines = await EvidenceBuilder._build_kline(conn, symbol)
            fund_flows = await EvidenceBuilder._build_fund_flows(conn, symbol)
            finance = await EvidenceBuilder._build_finance(conn, symbol)
            news = await EvidenceBuilder._build_news(conn, symbol)
            technical = await EvidenceBuilder._build_technical(conn, symbol)

            data_sources = []
            if quote:
                data_sources.append({"type": "quote", "source": quote.get("source", ""), "collected_at": quote.get("collected_at", "")})
            if klines:
                data_sources.append({"type": "kline", "source": klines[0].get("source", ""), "collected_at": klines[0].get("collected_at", "")})
            if fund_flows:
                data_sources.append({"type": "fund_flow", "source": fund_flows[0].get("source", ""), "collected_at": fund_flows[0].get("collected_at", "")})
            if finance:
                data_sources.append({"type": "finance", "source": finance.get("source", ""), "collected_at": finance.get("collected_at", "")})
            if news:
                data_sources.append({"type": "news", "source": "news_provider", "collected_at": ""})
            if technical:
                data_sources.append({"type": "technical", "source": technical.get("source", ""), "collected_at": technical.get("collected_at", "")})

            return {
                "symbol": symbol,
                "quote": quote,
                "kline": klines,
                "fund_flows": fund_flows,
                "finance": finance,
                "news": news,
                "technical": technical,
                "data_sources": data_sources,
            }
        finally:
            if close_conn:
                await conn.close()


    @staticmethod
    async def build_multi(symbols: list[str]) -> dict[str, dict]:
        """批量构建多个标的的证据包，用 WHERE IN 减少查询次数。"""
        if not symbols:
            return {}
        from backend.storage.database import aget_connection
        conn = await aget_connection()
        try:
            result: dict[str, dict] = {}
            # 批量查询各表
            placeholders = ",".join("?" for _ in symbols)
            params = list(symbols)

            # quotes
            quotes_map: dict[str, dict] = {}
            cursor = await conn.execute(
                f"""SELECT * FROM market_quotes
                    WHERE symbol IN ({placeholders})
                    AND collected_at IN (
                        SELECT MAX(collected_at) FROM market_quotes
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )""",
                params * 2,
            )
            for row in await cursor.fetchall():
                quotes_map[row["symbol"]] = dict(row)

            # klines
            cursor = await conn.execute(
                f"""SELECT * FROM kline_daily
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, date DESC""",
                params,
            )
            klines_by_symbol: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                if sym not in klines_by_symbol:
                    klines_by_symbol[sym] = []
                klines_by_symbol[sym].append(r)
                if len(klines_by_symbol[sym]) >= 60:
                    continue  # already have enough for this symbol

            # fund_flows
            cursor = await conn.execute(
                f"""SELECT * FROM fund_flows
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, date DESC""",
                params,
            )
            flows_by_symbol: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                if sym not in flows_by_symbol:
                    flows_by_symbol[sym] = []
                flows_by_symbol[sym].append(r)
                if len(flows_by_symbol[sym]) >= 5:
                    continue

            # finance
            cursor = await conn.execute(
                f"""SELECT * FROM financial_reports
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, collected_at DESC""",
                params,
            )
            fin_by_symbol: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                if sym not in fin_by_symbol:
                    fin_by_symbol[sym] = []
                fin_by_symbol[sym].append(r)

            # news
            # (news uses LIKE, can't batch easily; keep per-symbol for news)
            # technical
            cursor = await conn.execute(
                f"""SELECT * FROM technical_indicators
                    WHERE symbol IN ({placeholders})
                    AND date IN (
                        SELECT MAX(date) FROM technical_indicators
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )""",
                params * 2,
            )
            tech_map: dict[str, dict] = {}
            for row in await cursor.fetchall():
                tech_map[row["symbol"]] = dict(row)

            # Assemble per symbol
            for symbol in symbols:
                quote = quotes_map.get(symbol)
                klines = list(reversed(klines_by_symbol.get(symbol, [])[:60]))
                # 计算移动平均线（滑动窗口 O(n)）
                closes_k = [item["close"] for item in klines]
                ma_windows = (5, 10, 20, 60)
                running_sums: dict[int, float] = {w: 0.0 for w in ma_windows}
                for i, item in enumerate(klines):
                    c = closes_k[i]
                    for w in ma_windows:
                        running_sums[w] += c
                        if i >= w:
                            running_sums[w] -= closes_k[i - w]
                        if i >= w - 1:
                            item[f"ma{w}"] = round(running_sums[w] / w, 4)
                        else:
                            item[f"ma{w}"] = None
                flows = list(reversed(flows_by_symbol.get(symbol, [])[:5]))
                fin_rows = fin_by_symbol.get(symbol, [])
                finance = None
                if fin_rows:
                    latest = fin_rows[0]
                    if len(fin_rows) >= 2:
                        prev = fin_rows[1]
                        latest["prev_revenue"] = prev.get("revenue")
                        latest["prev_net_profit"] = prev.get("net_profit")
                        latest["prev_eps"] = prev.get("eps")
                        latest["prev_roe"] = prev.get("roe")
                    finance = latest

                # news by symbol
                news = None
                cursor = await conn.execute(
                    """SELECT * FROM news_items
                       WHERE EXISTS (SELECT 1 FROM json_each(related_symbols) WHERE value = ?)
                       AND published_at >= datetime("now", "-7 days")
                       ORDER BY published_at DESC""",
                    (symbol,),
                )
                news_rows = [dict(r) for r in await cursor.fetchall()]
                if news_rows:
                    sentiments = [item.get("sentiment", "neutral") for item in news_rows]
                    positive = sentiments.count("positive")
                    negative = sentiments.count("negative")
                    neutral = sentiments.count("neutral")
                    news = {
                        "positive_count": positive,
                        "negative_count": negative,
                        "neutral_count": neutral,
                        "total_count": len(news_rows),
                        "total": len(news_rows),
                        "latest": news_rows[:5],
                    }

                data_sources = []
                if quote:
                    data_sources.append({"type": "quote", "source": quote.get("source", ""), "collected_at": quote.get("collected_at", "")})
                if klines:
                    data_sources.append({"type": "kline", "source": klines[0].get("source", ""), "collected_at": klines[0].get("collected_at", "")})
                if flows:
                    data_sources.append({"type": "fund_flow", "source": flows[0].get("source", ""), "collected_at": flows[0].get("collected_at", "")})
                if finance:
                    data_sources.append({"type": "finance", "source": finance.get("source", ""), "collected_at": finance.get("collected_at", "")})
                if news:
                    data_sources.append({"type": "news", "source": "news_provider", "collected_at": ""})

                result[symbol] = {
                    "symbol": symbol,
                    "quote": quote,
                    "kline": klines,
                    "fund_flows": flows,
                    "finance": finance,
                    "news": news,
                    "technical": tech_map.get(symbol),
                    "data_sources": data_sources,
                }
            return result
        finally:
            await conn.close()

    @staticmethod
    async def _build_quote(conn, symbol: str) -> dict | None:
        cursor = await conn.execute(
            """SELECT * FROM market_quotes WHERE symbol = ?
               ORDER BY collected_at DESC LIMIT 1""",
            (symbol,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    async def _build_kline(conn, symbol: str) -> list[dict]:
        limits = EvidenceBuilder._evidence_limits()
        cursor = await conn.execute(
            """SELECT * FROM kline_daily WHERE symbol = ?
               ORDER BY date DESC LIMIT ?""",
            (symbol, limits["kline_limit"]),
        )
        rows = await cursor.fetchall()
        items = [dict(row) for row in rows]
        items.reverse()  # 按日期升序
        # 计算移动平均线（滑动窗口 O(n)）
        closes = [item["close"] for item in items]
        ma_windows = (5, 10, 20, 60)
        # 维护每个窗口的 running_sum，避免每次重新求和
        running_sums: dict[int, float] = {w: 0.0 for w in ma_windows}
        for i, item in enumerate(items):
            c = closes[i]
            for w in ma_windows:
                running_sums[w] += c
                if i >= w:
                    # 滑出最早一格
                    running_sums[w] -= closes[i - w]
                if i >= w - 1:
                    item[f"ma{w}"] = round(running_sums[w] / w, 4)
                else:
                    item[f"ma{w}"] = None
        return items

    @staticmethod
    async def _build_fund_flows(conn, symbol: str) -> list[dict]:
        limits = EvidenceBuilder._evidence_limits()
        cursor = await conn.execute(
            """SELECT * FROM fund_flows WHERE symbol = ?
               ORDER BY date DESC LIMIT ?""",
            (symbol, limits["fund_flow_limit"]),
        )
        rows = await cursor.fetchall()
        items = [dict(row) for row in rows]
        items.reverse()
        return items

    @staticmethod
    async def _build_finance(conn, symbol: str) -> dict | None:
        limits = EvidenceBuilder._evidence_limits()
        cursor = await conn.execute(
            """SELECT * FROM financial_reports WHERE symbol = ?
               ORDER BY collected_at DESC LIMIT ?""",
            (symbol, limits["finance_limit"]),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        latest = dict(rows[0])
        if len(rows) >= 2:
            prev = dict(rows[1])
            latest["prev_revenue"] = prev.get("revenue")
            latest["prev_net_profit"] = prev.get("net_profit")
            latest["prev_eps"] = prev.get("eps")
            latest["prev_roe"] = prev.get("roe")
        return latest

    @staticmethod
    async def _build_news(conn, symbol: str) -> dict | None:
        limits = EvidenceBuilder._evidence_limits()
        cursor = await conn.execute(
            """SELECT * FROM news_items
               WHERE EXISTS (SELECT 1 FROM json_each(related_symbols) WHERE value = ?)
               AND published_at >= datetime('now', ?)
               ORDER BY published_at DESC""",
            (symbol, f"-{limits['news_days']} days"),
        )
        rows = await cursor.fetchall()
        items = [dict(row) for row in rows]
        if not items:
            return None
        sentiments = [item.get("sentiment", "neutral") for item in items]
        positive = sentiments.count("positive")
        negative = sentiments.count("negative")
        neutral = sentiments.count("neutral")
        return {
            "total_count": len(items),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "latest": items[:5],
        }

    @staticmethod
    async def _build_technical(conn, symbol: str) -> dict | None:
        cursor = await conn.execute(
            """SELECT * FROM technical_indicators WHERE symbol = ?
               ORDER BY date DESC LIMIT 2""",
            (symbol,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        latest = dict(rows[0])
        if len(rows) >= 2:
            prev = dict(rows[1])
            latest["prev_macd_histogram"] = prev.get("macd_histogram")
        return latest

