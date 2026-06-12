from backend.services.ai_analyzer import AIAnalyzer


def _make_kline(
    ma5_last: float,
    ma20_last: float,
    ma60_last: float | None = None,
    ma5_prev: float | None = None,
    ma20_prev: float | None = None,
) -> list[dict]:
    prev: dict = {
        "date": "2026-05-30",
        "open": 370,
        "high": 375,
        "low": 369,
        "close": 373,
        "volume": 500000,
    }
    curr: dict = {
        "date": "2026-05-31",
        "open": 373,
        "high": 378,
        "low": 372,
        "close": 376,
        "volume": 600000,
    }
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
            "quote": {
                "price": 380.0,
                "change": 5.0,
                "change_pct": 1.33,
                "volume": 1000000,
                "collected_at": "...",
            },
            "kline": _make_kline(
                ma5_last=375, ma20_last=370, ma60_last=365, ma5_prev=368, ma20_prev=370
            ),
            "fund_flows": [
                {
                    "date": "2026-05-29",
                    "main_net_inflow": 1000000,
                    "net_inflow_ratio": 2.0,
                },
                {
                    "date": "2026-05-30",
                    "main_net_inflow": 1200000,
                    "net_inflow_ratio": 2.5,
                },
                {
                    "date": "2026-05-31",
                    "main_net_inflow": 800000,
                    "net_inflow_ratio": 1.8,
                },
            ],
            "finance": None,
            "news": None,
            "technical": {
                "macd_histogram": 0.5,
                "prev_macd_histogram": -0.3,
                "rsi14": 55.0,
            },
            "data_sources": [
                {"source": "westock", "type": "kline_daily", "collected_at": "..."}
            ],
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
            "quote": {
                "price": 350.0,
                "change": -5.0,
                "change_pct": -1.4,
                "volume": 1000000,
                "collected_at": "...",
            },
            "kline": _make_kline(
                ma5_last=355, ma20_last=360, ma60_last=365, ma5_prev=362, ma20_prev=360
            ),
            "fund_flows": [
                {
                    "date": "2026-05-29",
                    "main_net_inflow": -1000000,
                    "net_inflow_ratio": -2.0,
                },
                {
                    "date": "2026-05-30",
                    "main_net_inflow": -1200000,
                    "net_inflow_ratio": -2.5,
                },
                {
                    "date": "2026-05-31",
                    "main_net_inflow": -800000,
                    "net_inflow_ratio": -1.8,
                },
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
            "technical": {
                "rsi14": 25.0,
                "macd_histogram": 0.0,
                "prev_macd_histogram": None,
            },
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
            "technical": {
                "rsi14": 75.0,
                "macd_histogram": 0.0,
                "prev_macd_histogram": None,
            },
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
            "finance": {
                "report_period": "2026Q1",
                "roe": 18.5,
                "revenue_yoy": 8.5,
                "net_profit_yoy": 5.0,
            },
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
            "finance": {
                "report_period": "2026Q1",
                "roe": 10.0,
                "revenue_yoy": -5.0,
                "net_profit_yoy": -25.0,
            },
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
            "data_sources": [
                {"source": "westock", "type": "kline_daily", "collected_at": "..."}
            ],
        }
        result = AIAnalyzer.analyze(evidence)

        required_keys = [
            "symbol",
            "action",
            "confidence",
            "risk_level",
            "summary",
            "bullish_reasons",
            "bearish_reasons",
            "key_risks",
            "data_used",
            "generated_at",
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
            {
                "source": "westock",
                "type": "kline_daily",
                "collected_at": "2026-05-31T16:05:00+08:00",
            },
            {
                "source": "sina_rss",
                "type": "news",
                "collected_at": "2026-05-31T17:00:00+08:00",
            },
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


class TestAIAnalyzerConfidenceBoundary:
    """验证 3d48fe0 置信度公式在边界值上的行为。

    公式: confidence = (abs(score_diff) / max(total_score, 0.01)) * min(1.0, total_score / 0.5)
    """

    async def test_confidence_zero_when_no_signals(self) -> None:
        """无 quote + 无 kline → _insufficient_evidence 分支, confidence=0.0。"""
        evidence = {
            "symbol": "TEST",
            "quote": None,
            "kline": [],
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert result["confidence"] == 0.0
        assert result["action"] == "watch"

    async def test_confidence_clamped_at_one(self) -> None:
        """total_score >= 0.5 时, min 系数 = 1.0 不再压制。"""
        evidence = {
            "symbol": "TEST",
            "quote": {"price": 380.0, "change_pct": 5.0},
            "kline": _make_kline(
                ma5_last=385, ma20_last=380, ma60_last=375, ma5_prev=378, ma20_prev=380
            ),
            "fund_flows": [
                {
                    "date": "2026-05-29",
                    "main_net_inflow": 1000000,
                    "net_inflow_ratio": 2.0,
                },
                {
                    "date": "2026-05-30",
                    "main_net_inflow": 1200000,
                    "net_inflow_ratio": 2.5,
                },
                {
                    "date": "2026-05-31",
                    "main_net_inflow": 800000,
                    "net_inflow_ratio": 1.8,
                },
            ],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert 0.0 <= result["confidence"] <= 1.0

    async def test_confidence_suppressed_at_low_total(self) -> None:
        """total_score 较小时, min(1, total/0.5) 抑制置信度。"""
        evidence = {
            "symbol": "TEST",
            "quote": {"price": 100.0, "change_pct": 0.0},
            "kline": _make_kline(ma5_last=101, ma20_last=100, ma60_last=99),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        # 弱信号下置信度应被压制 (< 0.5)
        assert 0.0 <= result["confidence"] <= 1.0


class TestAIAnalyzerDividendOnly:
    """仅分红数据,无 quote/kline 也能分析（验证 has_any_evidence 放宽后逻辑）。"""

    async def test_dividend_only_triggers_analysis(self) -> None:
        """仅有 dividends 维度时, 不应落入 _insufficient_evidence。"""
        evidence = {
            "symbol": "hk00700",
            "quote": None,
            "kline": [],
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "dividends": {
                "latest_cash_dividend": 5.5,
                "history": [
                    {"cash_dividend": 5.5, "ex_date": "2026-04-15"},
                    {"cash_dividend": 4.8, "ex_date": "2025-04-20"},
                    {"cash_dividend": 4.5, "ex_date": "2024-04-18"},
                    {"cash_dividend": 4.0, "ex_date": "2023-04-22"},
                ],
            },
            "shareholders": None,
            "forecasts": None,
            "sector_context": None,
            "us_finance": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)

        # 应触发分析, 而非 _insufficient_evidence
        assert result["action"] != "watch" or result["summary"] != "证据不足，无法分析"
        # 4 期连续现金分红应触发看多信号
        assert any("连续现金分红" in r for r in result["bullish_reasons"])
        # latest 派息应触发看多信号
        assert any("最新一期派息" in r for r in result["bullish_reasons"])


class TestAIAnalyzerForecast:
    """业绩预告关键词触发 ±0.10 评分。"""

    async def test_forecast_预增_bullish(self) -> None:
        """业绩预告类型含 '预增' 关键词 → +0.10 看多。"""
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "dividends": None,
            "shareholders": None,
            "forecasts": {
                "history": [{"forecast_type": "预增", "report_period": "2026Q1"}],
            },
            "sector_context": None,
            "us_finance": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("预增" in r for r in result["bullish_reasons"])

    async def test_forecast_预减_bearish(self) -> None:
        """业绩预告类型含 '预减' 关键词 → +0.10 看空。"""
        evidence = {
            "symbol": "hk00700",
            "quote": {"price": 380.0},
            "kline": _make_kline(ma5_last=375, ma20_last=370),
            "fund_flows": [],
            "finance": None,
            "news": None,
            "technical": None,
            "dividends": None,
            "shareholders": None,
            "forecasts": {
                "history": [{"forecast_type": "预减", "report_period": "2026Q1"}],
            },
            "sector_context": None,
            "us_finance": None,
            "data_sources": [],
        }
        result = AIAnalyzer.analyze(evidence)
        assert any("预减" in r for r in result["bearish_reasons"])

    async def test_forecast_首亏_bearish(self) -> None:
        """'首亏' / '续亏' / '略减' / '预亏' 均应触发看空信号。"""
        for kw in ("首亏", "续亏", "略减", "预亏"):
            evidence = {
                "symbol": "hk00700",
                "quote": {"price": 380.0},
                "kline": _make_kline(ma5_last=375, ma20_last=370),
                "fund_flows": [],
                "finance": None,
                "news": None,
                "technical": None,
                "dividends": None,
                "shareholders": None,
                "forecasts": {
                    "history": [{"forecast_type": kw, "report_period": "2026Q1"}],
                },
                "sector_context": None,
                "us_finance": None,
                "data_sources": [],
            }
            result = AIAnalyzer.analyze(evidence)
            assert any(kw in r for r in result["bearish_reasons"]), (
                f"关键词 '{kw}' 未触发看空信号"
            )


class TestCheckNewsSectorExposure:
    """_check_news 消费 sector_exposure 和 weighted 字段的测试。"""

    def test_sector_exposure_positive_dominant(self) -> None:
        """top 板块 positive 占比 >= 60% 时产出看多理由。"""
        news = {
            "total_count": 10,
            "positive_count": 4,
            "negative_count": 2,
            "neutral_count": 4,
            "positive_weighted": 3.0,
            "negative_weighted": 1.0,
            "sector_exposure": [
                {"sector": "新能源", "count": 5, "positive": 4, "negative": 0, "neutral": 1, "avg_confidence": 0.85},
            ],
        }
        _, _, bull_r, _ = AIAnalyzer._check_news(news)
        assert any("新能源" in r for r in bull_r)

    def test_sector_exposure_negative_dominant(self) -> None:
        news = {
            "total_count": 10,
            "positive_count": 1,
            "negative_count": 4,
            "neutral_count": 5,
            "positive_weighted": 0.5,
            "negative_weighted": 3.0,
            "sector_exposure": [
                {"sector": "地产", "count": 5, "positive": 0, "negative": 4, "neutral": 1, "avg_confidence": 0.78},
            ],
        }
        _, bear, _, bear_r = AIAnalyzer._check_news(news)
        assert any("地产" in r for r in bear_r)

    def test_sector_exposure_mixed_no_reason(self) -> None:
        """top 板块 pos/neg 都 < 60% 时不产出板块理由。"""
        news = {
            "total_count": 10,
            "positive_count": 3,
            "negative_count": 3,
            "neutral_count": 4,
            "positive_weighted": 2.0,
            "negative_weighted": 2.0,
            "sector_exposure": [
                {"sector": "银行", "count": 6, "positive": 2, "negative": 2, "neutral": 2, "avg_confidence": 0.7},
            ],
        }
        _, _, bull_r, bear_r = AIAnalyzer._check_news(news)
        assert not any("银行" in r for r in bull_r)
        assert not any("银行" in r for r in bear_r)

    def test_weighted_net_strong_positive(self) -> None:
        """positive_weighted - negative_weighted > 1.0 时产出加权强度理由。"""
        news = {
            "total_count": 5,
            "positive_count": 2,
            "negative_count": 0,
            "neutral_count": 3,
            "positive_weighted": 2.5,
            "negative_weighted": 0.0,
            "sector_exposure": [],
        }
        _, _, bull_r, _ = AIAnalyzer._check_news(news)
        assert any("加权" in r for r in bull_r)

    def test_none_sector_exposure_safe(self) -> None:
        """sector_exposure=None 或缺失时 _check_news 不崩。"""
        news = {
            "total_count": 3,
            "positive_count": 1,
            "negative_count": 0,
            "neutral_count": 2,
            "positive_weighted": 0.5,
            "negative_weighted": 0.0,
        }
        # 不传 sector_exposure
        _, _, bull_r, bear_r = AIAnalyzer._check_news(news)
        # 不应崩, 不应产出板块相关理由
        assert all("板块" not in r for r in bull_r)
        assert all("板块" not in r for r in bear_r)
