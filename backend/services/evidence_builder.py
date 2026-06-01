from datetime import datetime, timedelta, timezone

import pandas as pd
from loguru import logger

from backend.storage.database import get_db


class EvidenceBuilder:
    """为 AI 分析准备结构化输入数据，确保分析基于真实采集数据。"""

    @staticmethod
    def build(symbol: str) -> dict:
        quote = EvidenceBuilder._build_quote(symbol)
        kline = EvidenceBuilder._build_kline(symbol)
        fund_flows = EvidenceBuilder._build_fund_flows(symbol)
        finance = EvidenceBuilder._build_finance(symbol)
        news = EvidenceBuilder._build_news(symbol)
        technical = EvidenceBuilder._build_technical(symbol)
        data_sources = EvidenceBuilder._collect_data_sources(
            symbol, quote, kline, fund_flows, finance, news, technical
        )
        evidence = {
            "symbol": symbol,
            "quote": quote,
            "kline": kline,
            "fund_flows": fund_flows,
            "finance": finance,
            "news": news,
            "technical": technical,
            "data_sources": data_sources,
        }
        logger.info("证据包组装完成: symbol={}, 数据源数={}", symbol, len(data_sources))
        return evidence

    @staticmethod
    def _build_quote(symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT price, change, change_pct, volume, source, collected_at
                   FROM market_quotes WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["_source"] = result["source"]
        result["_collected_at"] = result["collected_at"]
        return result

    @staticmethod
    def _build_kline(symbol: str) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT date, open, high, low, close, volume, source, collected_at
                   FROM kline_daily WHERE symbol = ?
                   ORDER BY date DESC LIMIT 60""",
                (symbol,),
            ).fetchall()
        if not rows:
            return []
        latest_source = rows[0]["source"] if rows else None
        latest_collected_at = rows[0]["collected_at"] if rows else None
        items = [dict(r) for r in reversed(rows)]
        df = pd.DataFrame(items)
        for window in [5, 10, 20, 60]:
            col = f"ma{window}"
            df[col] = df["close"].rolling(window=window, min_periods=window).mean()
        result = df.to_dict(orient="records")
        for item in result:
            for key in ["ma5", "ma10", "ma20", "ma60"]:
                val = item.get(key)
                if pd.isna(val):
                    item[key] = None
                else:
                    item[key] = round(float(val), 4)
            item.pop("source", None)
            item.pop("collected_at", None)
        if result:
            result[-1]["_source"] = latest_source
            result[-1]["_collected_at"] = latest_collected_at
        return result

    @staticmethod
    def _build_fund_flows(symbol: str) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT date, main_net_inflow, net_inflow_ratio, source, collected_at
                   FROM fund_flows WHERE symbol = ?
                   ORDER BY date DESC LIMIT 5""",
                (symbol,),
            ).fetchall()
        if not rows:
            return []
        return [dict(r) for r in rows]

    @staticmethod
    def _build_finance(symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT report_period, revenue, revenue_yoy, net_profit,
                          net_profit_yoy, eps, roe, debt_ratio, gross_margin, net_margin,
                          source, collected_at
                   FROM financial_reports WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["_source"] = result["source"]
        result["_collected_at"] = result["collected_at"]
        return result

    @staticmethod
    def _build_news(symbol: str) -> dict | None:
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with get_db() as conn:
            rows = conn.execute(
                """SELECT title, sentiment, published_at, source, collected_at
                   FROM news_items
                   WHERE related_symbols LIKE ? AND published_at >= ?
                   ORDER BY published_at DESC""",
                (f"%{symbol}%", seven_days_ago),
            ).fetchall()
        if not rows:
            return None
        items = [dict(r) for r in rows]
        positive_count = sum(1 for i in items if i.get("sentiment") == "positive")
        negative_count = sum(1 for i in items if i.get("sentiment") == "negative")
        neutral_count = sum(1 for i in items if i.get("sentiment") == "neutral")
        total_count = len(items)
        return {
            "items": items,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "total_count": total_count,
            "_source": items[0].get("source") if items else None,
            "_collected_at": items[0].get("collected_at") if items else None,
        }

    @staticmethod
    def _build_technical(symbol: str) -> dict | None:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT symbol, date, ma5, ma10, ma20, ma60,
                          macd_dif, macd_dea, macd_histogram,
                          rsi6, rsi14,
                          boll_upper, boll_middle, boll_lower,
                          source, collected_at
                   FROM technical_indicators WHERE symbol = ?
                   ORDER BY date DESC LIMIT 2""",
                (symbol,),
            ).fetchall()
        if not rows:
            return None
        latest = dict(rows[0])
        result: dict = {
            "ma5": latest.get("ma5"),
            "ma10": latest.get("ma10"),
            "ma20": latest.get("ma20"),
            "ma60": latest.get("ma60"),
            "macd_dif": latest.get("macd_dif"),
            "macd_dea": latest.get("macd_dea"),
            "macd_histogram": latest.get("macd_histogram"),
            "rsi6": latest.get("rsi6"),
            "rsi14": latest.get("rsi14"),
            "boll_upper": latest.get("boll_upper"),
            "boll_middle": latest.get("boll_middle"),
            "boll_lower": latest.get("boll_lower"),
            "_source": latest.get("source"),
            "_collected_at": latest.get("collected_at"),
        }
        if len(rows) >= 2:
            prev = dict(rows[1])
            result["prev_macd_histogram"] = prev.get("macd_histogram")
        else:
            result["prev_macd_histogram"] = None
        return result

    @staticmethod
    def _collect_data_sources(
        symbol: str,
        quote: dict | None,
        kline: list[dict],
        fund_flows: list[dict],
        finance: dict | None,
        news: dict | None,
        technical: dict | None,
    ) -> list[dict]:
        sources: list[dict] = []
        if quote is not None:
            src = quote.get("_source")
            cat = quote.get("_collected_at")
            if src is not None:
                sources.append({"source": src, "type": "market_quotes", "collected_at": cat})
        if kline:
            last = kline[-1]
            src = last.get("_source")
            cat = last.get("_collected_at")
            if src is not None:
                sources.append({"source": src, "type": "kline_daily", "collected_at": cat})
        if fund_flows:
            first = fund_flows[0]
            src = first.get("source")
            cat = first.get("collected_at")
            if src is not None:
                sources.append({"source": src, "type": "fund_flows", "collected_at": cat})
        if finance is not None:
            src = finance.get("_source")
            cat = finance.get("_collected_at")
            if src is not None:
                sources.append({"source": src, "type": "financial_reports", "collected_at": cat})
        if news is not None:
            src = news.get("_source")
            cat = news.get("_collected_at")
            if src is not None:
                sources.append({"source": src, "type": "news", "collected_at": cat})
        if technical is not None:
            src = technical.get("_source")
            cat = technical.get("_collected_at")
            if src is not None:
                sources.append({"source": src, "type": "technical_indicators", "collected_at": cat})
        return sources
