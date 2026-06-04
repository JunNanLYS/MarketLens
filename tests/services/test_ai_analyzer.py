from datetime import datetime, timezone

import pytest
from backend.services.ai_analyzer import AIAnalyzer


def _make_kline(ma5_last: float, ma20_last: float, ma60_last: float | None = None,
                ma5_prev: float | None = None, ma20_prev: float | None = None) -> list[dict]:
    prev: dict = {"date": "2026-05-30", "open": 370, "high": 375, "low": 369, "close": 373, "volume": 500000}
    curr: dict = {"date": "2026-05-31", "open": 373, "high": 378, "low": 372, "close": 376, "volume": 600000}
    if ma5_prev is not None:
        prev["ma5"] = ma5_prev
    if ma20_prev is not None:
        prev["ma20"] = ma20_prev
    curr["ma5"] = ma5_last
    curr["ma20"] = ma20_last
    if ma60_last is not None:
        curr["ma60"] = ma60_last
    return [prev, curr]


class TestAIAnalyzerBullish:
    """多头信号。"""

    async def test_bullish_alignment_with_inflow_and_golden_cross(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0, "change": 5.0, "change_pct": 1.33, "volume": 1000000, "collected_at": "..."},
            "kline": _make_kline(ma5_last=375, ma20_last=370, ma60_last=365, ma5_prev=368, ma20_prev=370),
            "fund_flows": [
                {"date": "2026-05-29", "main_net_inflow": 1000000, "net_inflow_ratio": 2.0},
                {"date": "2026-05-30", "main_net_inflow": 1200000, "net_inflow_ratio": 2.5},
                {"date": "2026-05-31", "main_net_inflow": 800000, "net_inflow_ratio": 1.8},
            ],
            "finance": None,
            "news": None,
            "technical": {
                "macd_histogram": 0.5,
                "prev_macd_histogram": -0.3,
                "rsi14": 55.0,
            },
            "data_sources": [{"source": "westock", "type": "kline_daily", "collected_at": "..."}],
        }
        result = AIAnalyzer.analyze(evidence)

        assert result["action"] == "buy"
        assert result["confidence"] > 0
        assert "MA5 > MA20 > MA60 多头排列" in result["bullish_reasons"]
        assert "MA5 上穿 MA20" in result["bullish_reasons"]
        assert "连续 3 日主力净流入" in result["bullish_reasons"]
        assert "MACD 金叉" in result["bullish_reasons"]
        assert result["symbol"] == "hk00700"
        assert "data_used" in result


class TestAIAnalyzerBearish:
    """空头信号。"""

    async def test_bearish_alignment_with_outflow_and_death_cross(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 350.0, "change": -5.0, "change_pct": -1.4, "volume": 1000000, "collected_at": "..."},
            "kline": _make_kline(ma5_last=355, ma20_last=360, ma60_last=365, ma5_prev=362, ma20_prev=360),
            "fund_flows": [
                {"date": "2026-05-29", "main_net_inflow": -1000000, "net_inflow_ratio": -2.0},
                {"date": "2026-05-30", "main_net_inflow": -1200000, "net_inflow_ratio": -2.5},
                {"date": "2026-05-31", "main_net_inflow": -800000, "net_inflow_ratio": -1.8},
            ],
            "finance": None,
            "news": None,
            "technical": {
                "macd_histogram": -0.5,
                "prev_macd_histogram": 0.3,
                "rsi14": 55.0,
            },
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)

        assert result["action"] == "sell"
        assert "MA5 < MA20 < MA60 空头排列" in result["bearish_reasons"]
        assert "MA5 下穿 MA20" in result["bearish_reasons"]
        assert "连续 3 日主力净流出" in result["bearish_reasons"]
        assert "MACD 死叉" in result["bearish_reasons"]


class TestAIAnalyzerInsufficient:
    """证据不足时输出 action=watch, confidence=0。"""

    async def test_no_quote_no_kline(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": None,
            "kline": [],
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)

        assert result["action"] == "watch"
        assert result["confidence"] == 0.0
        assert result["summary"] == "证据不足，无法分析"
        assert result["bullish_reasons"] == []
        assert result["bearish_reasons"] == []
        assert result["key_risks"] == []

    async def test_only_quote_no_kline(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": [],
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert result["action"] == "watch"


class TestAIAnalyzerRSI:
    """RSI 超买超卖。"""

    async def test_rsi_oversold(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 300.0},
            "kline": _make_kline(ma5_last=305, ma20_last=310),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": {"rsi14": 25.0, "macd_histogram": 0.0, "prev_macd_histogram": None},
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("超卖" in r for r in result["bullish_reasons"])

    async def test_rsi_overbought(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 400.0},
            "kline": _make_kline(ma5_last=395, ma20_last=390),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": {"rsi14": 75.0, "macd_histogram": 0.0, "prev_macd_histogram": None},
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("超买" in r for r in result["bearish_reasons"])


class TestAIAnalyzerNews:
    """新闻情绪影响。"""

    async def test_positive_news(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": {
                "items": [],
                "positive_count": 7,
                "negative_count": 1,
                "neutral_count": 2,
                "total_count": 10,
            },
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("正面新闻占比" in r for r in result["bullish_reasons"])

    async def test_negative_news(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": {
                "items": [],
                "positive_count": 1,
                "negative_count": 5,
                "neutral_count": 2,
                "total_count": 8,
            },
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("负面新闻占比" in r for r in result["bearish_reasons"])


class TestAIAnalyzerFinance:
    """财务指标影响。"""

    async def test_roe_positive_revenue(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": {"report_period": "2026Q1", "roe": 18.5, "revenue_yoy": 8.5, "net_profit_yoy": 5.0},
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("ROE" in r and "营收正增长" in r for r in result["bullish_reasons"])

    async def test_net_profit_decline(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": {"report_period": "2026Q1", "roe": 10.0, "revenue_yoy": -5.0, "net_profit_yoy": -25.0},
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("净利润同比负增长" in r for r in result["bearish_reasons"])


class TestAIAnalyzerSchema:
    """输出 JSON 格式校验（字段完整性）。"""

    async def test_output_schema(self) -> None:
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [{"source": "westock", "type": "kline_daily", "collected_at": "..."}],
        }
        result = AIAnalyzer.analyze(evidence)

        required_keys = [
            "symbol", "action", "confidence", "risk_level", "summary",
            "bullish_reasons", "bearish_reasons", "key_risks", "data_used", "generated_at",
        ]
        for key in required_keys:
            assert key in result, f"缺少字段: {key}"

        assert result["action"] in ("buy", "sell", "watch", "avoid")
        assert result["risk_level"] in ("low", "medium", "high")
        assert isinstance(result["confidence"], float)
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result["bullish_reasons"], list)
        assert isinstance(result["bearish_reasons"], list)
        assert isinstance(result["key_risks"], list)
        assert isinstance(result["data_used"], list)
        assert isinstance(result["generated_at"], str)


class TestAIAnalyzerDataUsed:
    """data_used 字段正确。"""

    async def test_data_used_from_evidence(self) -> None:
        data_sources = [
            {"source": "westock", "type": "kline_daily", "collected_at": "2026-05-31T16:05:00+08:00"},
            {"source": "sina_rss", "type": "news", "collected_at": "2026-05-31T17:00:00+08:00"},
        ]
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": data_sources,
        }
        result = AIAnalyzer.analyze(evidence)
        assert result["data_used"] == data_sources
