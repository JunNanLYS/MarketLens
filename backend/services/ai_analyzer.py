from datetime import datetime, timezone

from loguru import logger


class AIAnalyzer:
    """规则型分析引擎，基于预设规则矩阵对证据包进行分析。"""

    @staticmethod
    def analyze(evidence: dict) -> dict:
        symbol = evidence.get("symbol", "")
        quote = evidence.get("quote")
        kline = evidence.get("kline", [])
        fund_flows = evidence.get("fund_flows", [])
        finance = evidence.get("finance")
        news = evidence.get("news")
        technical = evidence.get("technical")
        data_sources = evidence.get("data_sources", [])

        if quote is None and not kline:
            return AIAnalyzer._insufficient_evidence(symbol, data_sources)

        bullish_score = 0.0
        bearish_score = 0.0
        bullish_reasons: list[str] = []
        bearish_reasons: list[str] = []

        trend_bull, trend_bear, trend_bull_r, trend_bear_r = AIAnalyzer._check_trend(kline)
        bullish_score += trend_bull
        bearish_score += trend_bear
        bullish_reasons.extend(trend_bull_r)
        bearish_reasons.extend(trend_bear_r)

        fund_bull, fund_bear, fund_bull_r, fund_bear_r = AIAnalyzer._check_fund_flow(fund_flows)
        bullish_score += fund_bull
        bearish_score += fund_bear
        bullish_reasons.extend(fund_bull_r)
        bearish_reasons.extend(fund_bear_r)

        tech_bull, tech_bear, tech_bull_r, tech_bear_r = AIAnalyzer._check_technical(technical)
        bullish_score += tech_bull
        bearish_score += tech_bear
        bullish_reasons.extend(tech_bull_r)
        bearish_reasons.extend(tech_bear_r)

        news_bull, news_bear, news_bull_r, news_bear_r = AIAnalyzer._check_news(news)
        bullish_score += news_bull
        bearish_score += news_bear
        bullish_reasons.extend(news_bull_r)
        bearish_reasons.extend(news_bear_r)

        fin_bull, fin_bear, fin_bull_r, fin_bear_r = AIAnalyzer._check_finance(finance)
        bullish_score += fin_bull
        bearish_score += fin_bear
        bullish_reasons.extend(fin_bull_r)
        bearish_reasons.extend(fin_bear_r)

        score_diff = bullish_score - bearish_score
        total_score = bullish_score + bearish_score
        confidence = abs(score_diff) / max(total_score, 0.01)

        if score_diff > 0.3:
            action = "buy"
        elif score_diff > 0.1:
            action = "watch"
        elif score_diff < -0.3:
            action = "sell"
        elif score_diff < -0.1:
            action = "watch"
        else:
            action = "watch"

        if confidence > 0.6 and bearish_score > 0.2:
            risk_level = "high"
        elif confidence > 0.3:
            risk_level = "medium"
        else:
            risk_level = "low"

        key_risks = bearish_reasons.copy()

        summary = AIAnalyzer._generate_summary(
            action, score_diff, bullish_reasons, bearish_reasons, news, finance
        )

        result = {
            "symbol": symbol,
            "action": action,
            "confidence": round(confidence, 4),
            "risk_level": risk_level,
            "summary": summary,
            "bullish_reasons": bullish_reasons,
            "bearish_reasons": bearish_reasons,
            "key_risks": key_risks,
            "data_used": data_sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("AI 分析完成: symbol={}, action={}, confidence={}", symbol, action, result["confidence"])
        return result

    @staticmethod
    def _insufficient_evidence(symbol: str, data_sources: list[dict]) -> dict:
        return {
            "symbol": symbol,
            "action": "watch",
            "confidence": 0.0,
            "risk_level": "low",
            "summary": "证据不足，无法分析",
            "bullish_reasons": [],
            "bearish_reasons": [],
            "key_risks": [],
            "data_used": data_sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _check_trend(kline: list[dict]) -> tuple[float, float, list[str], list[str]]:
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if not kline or len(kline) < 2:
            return bullish, bearish, bull_reasons, bear_reasons

        latest = kline[-1]
        ma5 = latest.get("ma5")
        ma20 = latest.get("ma20")
        ma60 = latest.get("ma60")
        if ma5 is not None and ma20 is not None and ma60 is not None:
            if ma5 > ma20 > ma60:
                bullish += 0.20
                bull_reasons.append("MA5 > MA20 > MA60 多头排列")
            if ma5 < ma20 < ma60:
                bearish += 0.20
                bear_reasons.append("MA5 < MA20 < MA60 空头排列")

        prev = kline[-2]
        curr = kline[-1]
        prev_ma5 = prev.get("ma5")
        prev_ma20 = prev.get("ma20")
        curr_ma5 = curr.get("ma5")
        curr_ma20 = curr.get("ma20")
        if all(v is not None for v in [prev_ma5, prev_ma20, curr_ma5, curr_ma20]):
            if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20:
                bullish += 0.15
                bull_reasons.append("MA5 上穿 MA20")
            if prev_ma5 > prev_ma20 and curr_ma5 < curr_ma20:
                bearish += 0.15
                bear_reasons.append("MA5 下穿 MA20")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_fund_flow(fund_flows: list[dict]) -> tuple[float, float, list[str], list[str]]:
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if not fund_flows or len(fund_flows) < 3:
            return bullish, bearish, bull_reasons, bear_reasons

        consecutive_inflow = 0
        consecutive_outflow = 0
        for item in fund_flows:
            inflow = item.get("main_net_inflow")
            if inflow is not None and inflow > 0:
                consecutive_inflow += 1
                consecutive_outflow = 0
            elif inflow is not None and inflow < 0:
                consecutive_outflow += 1
                consecutive_inflow = 0
            else:
                consecutive_inflow = 0
                consecutive_outflow = 0

        if consecutive_inflow >= 3:
            bullish += 0.15
            bull_reasons.append(f"连续 {consecutive_inflow} 日主力净流入")
        if consecutive_outflow >= 3:
            bearish += 0.15
            bear_reasons.append(f"连续 {consecutive_outflow} 日主力净流出")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_technical(technical: dict | None) -> tuple[float, float, list[str], list[str]]:
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if technical is None:
            return bullish, bearish, bull_reasons, bear_reasons

        rsi14 = technical.get("rsi14")
        if rsi14 is not None:
            if rsi14 < 30:
                bullish += 0.05
                bull_reasons.append(f"RSI14={rsi14:.1f}，超卖区间")
            if rsi14 > 70:
                bearish += 0.05
                bear_reasons.append(f"RSI14={rsi14:.1f}，超买区间")

        curr_hist = technical.get("macd_histogram")
        prev_hist = technical.get("prev_macd_histogram")
        if curr_hist is not None and prev_hist is not None:
            if prev_hist < 0 and curr_hist > 0:
                bullish += 0.10
                bull_reasons.append("MACD 金叉")
            if prev_hist > 0 and curr_hist < 0:
                bearish += 0.10
                bear_reasons.append("MACD 死叉")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_news(news: dict | None) -> tuple[float, float, list[str], list[str]]:
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if news is None:
            return bullish, bearish, bull_reasons, bear_reasons

        total = news.get("total_count", 0)
        if total > 0:
            positive_pct = news.get("positive_count", 0) / total
            negative_pct = news.get("negative_count", 0) / total
            if positive_pct > 0.6:
                bullish += 0.05
                bull_reasons.append(f"正面新闻占比 {positive_pct:.0%}")
            if negative_pct > 0.4:
                bearish += 0.05
                bear_reasons.append(f"负面新闻占比 {negative_pct:.0%}")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_finance(finance: dict | None) -> tuple[float, float, list[str], list[str]]:
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if finance is None:
            return bullish, bearish, bull_reasons, bear_reasons

        roe = finance.get("roe")
        revenue_yoy = finance.get("revenue_yoy")
        net_profit_yoy = finance.get("net_profit_yoy")

        if roe is not None and revenue_yoy is not None:
            if roe > 15 and revenue_yoy > 0:
                bullish += 0.10
                bull_reasons.append(f"ROE={roe:.1f}% 且营收正增长")

        if net_profit_yoy is not None:
            if net_profit_yoy < -20:
                bearish += 0.10
                bear_reasons.append(f"净利润同比负增长 {net_profit_yoy:.1f}%")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _generate_summary(
        action: str,
        score_diff: float,
        bullish_reasons: list[str],
        bearish_reasons: list[str],
        news: dict | None,
        finance: dict | None,
    ) -> str:
        parts: list[str] = []
        if score_diff > 0.3:
            parts.append("多头信号较强")
        elif score_diff > 0.1:
            parts.append("短期偏多")
        elif score_diff < -0.3:
            parts.append("空头信号较强")
        elif score_diff < -0.1:
            parts.append("短期偏空")
        else:
            parts.append("趋势震荡")

        if news is not None:
            total = news.get("total_count", 0)
            if total > 0:
                positive_pct = news.get("positive_count", 0) / total
                negative_pct = news.get("negative_count", 0) / total
                if positive_pct > 0.6:
                    parts.append("新闻偏正面")
                elif negative_pct > 0.4:
                    parts.append("新闻偏负面")
                else:
                    parts.append("新闻情绪中性")

        if finance is not None:
            net_profit_yoy = finance.get("net_profit_yoy")
            if net_profit_yoy is not None and net_profit_yoy < -20:
                parts.append("盈利能力下滑")

        if not bullish_reasons and not bearish_reasons:
            parts.append("资金面尚未确认")

        return "，".join(parts) + "。"
