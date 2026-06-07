"""规则型 AI 分析引擎 —— 信号评分、风险评估与投资建议生成。"""
from datetime import datetime, timezone

from loguru import logger


# 信号评分阈值
SIGNAL_BULLISH_STRONG = 0.3    # 信号 > 0.3 发出强烈买入信号
SIGNAL_BULLISH_WEAK = 0.1      # 信号 > 0.1 发出弱买入信号
SIGNAL_BEARISH_STRONG = -0.3   # 信号 < -0.3 发出强烈卖出信号
SIGNAL_BEARISH_WEAK = -0.1     # 信号 < -0.1 发出弱卖出信号

RISK_HIGH_THRESHOLD = 0.6      # 风险 > 0.6 且信号 > 0.2 为高风险
RISK_MEDIUM_THRESHOLD = 0.3    # 风险 > 0.3 为中高风险警告
RISK_BEARISH_MIN = 0.2         # 看跌信号超 0.2 触发风险预警

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
        dividends = evidence.get("dividends")
        shareholders = evidence.get("shareholders")
        forecasts = evidence.get("forecasts")
        sector_ctx = evidence.get("sector_context")
        us_finance = evidence.get("us_finance")
        data_sources = evidence.get("data_sources", [])

        # 放宽证据不足判定：允许 quote/kline 缺失但有其他证据维度时继续分析
        has_any_evidence = bool(
            quote is not None
            or kline
            or dividends
            or shareholders
            or forecasts
            or sector_ctx
            or us_finance
        )
        if not has_any_evidence:
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

        # 5 个新增证据维度评分（evidence-driven AI 约束：每条数据必须被使用）
        div_bull, div_bear, div_bull_r, div_bear_r = AIAnalyzer._check_dividend(dividends)
        bullish_score += div_bull
        bearish_score += div_bear
        bullish_reasons.extend(div_bull_r)
        bearish_reasons.extend(div_bear_r)

        shr_bull, shr_bear, shr_bull_r, shr_bear_r = AIAnalyzer._check_shareholder(shareholders)
        bullish_score += shr_bull
        bearish_score += shr_bear
        bullish_reasons.extend(shr_bull_r)
        bearish_reasons.extend(shr_bear_r)

        fc_bull, fc_bear, fc_bull_r, fc_bear_r = AIAnalyzer._check_forecast(forecasts)
        bullish_score += fc_bull
        bearish_score += fc_bear
        bullish_reasons.extend(fc_bull_r)
        bearish_reasons.extend(fc_bear_r)

        sec_bull, sec_bear, sec_bull_r, sec_bear_r = AIAnalyzer._check_sector_context(sector_ctx)
        bullish_score += sec_bull
        bearish_score += sec_bear
        bullish_reasons.extend(sec_bull_r)
        bearish_reasons.extend(sec_bear_r)

        usfin_bull, usfin_bear, usfin_bull_r, usfin_bear_r = AIAnalyzer._check_us_finance(us_finance)
        bullish_score += usfin_bull
        bearish_score += usfin_bear
        bullish_reasons.extend(usfin_bull_r)
        bearish_reasons.extend(usfin_bear_r)

        score_diff = bullish_score - bearish_score
        total_score = bullish_score + bearish_score
        # 置信度：相对差异 * 绝对强度系数。
        # 当 total_score 较小时（信号极弱），min(1, total/0.5) 抑制置信度，
        # 避免在证据不足时返回接近 100% 的虚假高置信度。
        confidence = (abs(score_diff) / max(total_score, 0.01)) * min(1.0, total_score / 0.5)

        if score_diff > SIGNAL_BULLISH_STRONG:
            action = "buy"
        elif score_diff > SIGNAL_BULLISH_WEAK:
            action = "watch"
        elif score_diff < SIGNAL_BEARISH_STRONG:
            action = "sell"
        elif score_diff < SIGNAL_BEARISH_WEAK:
            action = "watch"
        else:
            action = "watch"

        if confidence > RISK_HIGH_THRESHOLD and bearish_score > RISK_BEARISH_MIN:
            risk_level = "high"
        elif confidence > RISK_MEDIUM_THRESHOLD:
            risk_level = "medium"
        else:
            risk_level = "low"

        # key_risks 与 bearish_reasons 同源会导致 UI 显示两份相同列表
        # 改为独立字段：基于 risk_level==high 时高危信号的精简子集
        if risk_level == "high":
            key_risks = [r for r in bearish_reasons if any(
                kw in r for kw in ("风险", "亏损", "负增长", "减持", "看空", "下跌", "利空")
            )][:5]
        else:
            key_risks = []

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
                if consecutive_outflow > 0:
                    break
                consecutive_inflow += 1
            elif inflow is not None and inflow < 0:
                if consecutive_inflow > 0:
                    break
                consecutive_outflow += 1
            else:
                break

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
        """财务信号评分。

        净利润同比读数（``net_profit_yoy``）以 ``(curr - prev) / abs(prev) * 100``
        形式给出，**单凭百分比会掩盖"扭亏 / 亏损收窄"等符号翻转语义**。
        因此同时读取 ``net_profit_yoy_sign`` 结构化标签（由
        ``EvidenceBuilder._classify_yoy_sign`` 产出），仅在
        ``sign == "normal"`` 且 ``yoy < -20`` 时才判定为看空；
        "turnaround" / "loss_narrowing" 被视为**改善信号**（+ 看多），
        避免对扭亏为盈 / 亏损收窄的标的产生误导。
        """
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if finance is None:
            return bullish, bearish, bull_reasons, bear_reasons

        roe = finance.get("roe")
        revenue_yoy = finance.get("revenue_yoy")
        net_profit_yoy = finance.get("net_profit_yoy")
        net_profit_yoy_sign = finance.get("net_profit_yoy_sign")

        if roe is not None and revenue_yoy is not None:
            if roe > 15 and revenue_yoy > 0:
                bullish += 0.10
                bull_reasons.append(f"ROE={roe:.1f}% 且营收正增长")

        if net_profit_yoy is not None:
            if net_profit_yoy_sign in ("turnaround", "loss_narrowing"):
                # 符号翻转或亏损收窄 —— 经济意义是改善，给看多信号
                bullish += 0.10
                label = "扭亏为盈" if net_profit_yoy_sign == "turnaround" else "亏损收窄"
                bull_reasons.append(f"净利润{label}（同比 {net_profit_yoy:+.1f}%）")
            elif net_profit_yoy_sign == "loss_widening":
                # 亏损扩大 —— 实质是看空信号（百分比"下降"不代表业绩好转）
                bearish += 0.10
                bear_reasons.append(f"净利润亏损扩大（同比 {net_profit_yoy:+.1f}%）")
            elif net_profit_yoy < -20:
                # normal 情形下的传统阈值（保持向后兼容）
                bearish += 0.10
                bear_reasons.append(f"净利润同比负增长 {net_profit_yoy:.1f}%")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_dividend(dividends: dict | None) -> tuple[float, float, list[str], list[str]]:
        """分红信号：最近一期派息 + 连续性。"""
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if dividends is None:
            return bullish, bearish, bull_reasons, bear_reasons

        latest_cash = dividends.get("latest_cash_dividend")
        history = dividends.get("history", [])

        if latest_cash is not None and latest_cash > 0:
            bullish += 0.05
            bull_reasons.append(f"最新一期派息 {latest_cash:.2f} 元/股")

        # 连续性：最近 4 期中现金分红 > 0 的比例
        if history and len(history) >= 4:
            paying_count = sum(1 for h in history if (h.get("cash_dividend") or 0) > 0)
            if paying_count == 0:
                bearish += 0.05
                bear_reasons.append("最近 4 期均无现金分红")
            elif paying_count == 4:
                bullish += 0.05
                bull_reasons.append("最近 4 期连续现金分红")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_shareholder(shareholders: dict | None) -> tuple[float, float, list[str], list[str]]:
        """股东结构信号：股东人数趋势（筹码集中/分散）。"""
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if shareholders is None:
            return bullish, bearish, bull_reasons, bear_reasons

        trend = shareholders.get("holder_count_trend", [])
        if len(trend) >= 2:
            # 较早期 vs 最新：人数下降 = 筹码集中
            recent = trend[-1].get("holder_count", 0)
            earlier = trend[0].get("holder_count", 0)
            if recent and earlier and recent < earlier:
                bullish += 0.05
                bull_reasons.append(f"股东人数从 {earlier} 降至 {recent}，筹码集中")
            elif recent and earlier and recent > earlier:
                bearish += 0.05
                bear_reasons.append(f"股东人数从 {earlier} 升至 {recent}，筹码分散")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_forecast(forecasts: dict | None) -> tuple[float, float, list[str], list[str]]:
        """业绩预告信号：最新一期的 forecast_type。"""
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if forecasts is None:
            return bullish, bearish, bull_reasons, bear_reasons

        history = forecasts.get("history", [])
        if not history:
            return bullish, bearish, bull_reasons, bear_reasons

        latest_type = history[0].get("forecast_type", "")
        # 业绩预告类型关键词匹配（业务语言："预增"/"扭亏"为看多；"预减"/"首亏"为看空）
        if any(kw in latest_type for kw in ("预增", "扭亏", "续盈", "略增")):
            bullish += 0.10
            bull_reasons.append(f"业绩预告：{latest_type}")
        elif any(kw in latest_type for kw in ("预减", "首亏", "续亏", "略减", "预亏")):
            bearish += 0.10
            bear_reasons.append(f"业绩预告：{latest_type}")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_sector_context(sector_ctx: dict | None) -> tuple[float, float, list[str], list[str]]:
        """板块背景：所处行业 / 概念在 Top 涨幅榜为加分，Top 跌幅榜为减分。"""
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if sector_ctx is None:
            return bullish, bearish, bull_reasons, bear_reasons

        top_gainers = sector_ctx.get("top_gainers", [])
        top_losers = sector_ctx.get("top_losers", [])

        if top_gainers:
            top_sector = top_gainers[0].get("sector_name", "")
            if top_sector:
                bullish += 0.05
                bull_reasons.append(f"行业板块 {top_sector} 领涨大盘")

        if top_losers:
            bottom_sector = top_losers[0].get("sector_name", "")
            if bottom_sector:
                bearish += 0.05
                bear_reasons.append(f"行业板块 {bottom_sector} 领跌大盘")

        return bullish, bearish, bull_reasons, bear_reasons

    @staticmethod
    def _check_us_finance(us_finance: dict | None) -> tuple[float, float, list[str], list[str]]:
        """美股财务信号：年化营收同比。"""
        bullish = 0.0
        bearish = 0.0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        if us_finance is None:
            return bullish, bearish, bull_reasons, bear_reasons

        annual = us_finance.get("annual", [])
        if not annual or len(annual) < 2:
            return bullish, bearish, bull_reasons, bear_reasons

        # 简化：取最近两期 revenue 计算 yoy
        latest = annual[0].get("revenue")
        prev = annual[1].get("revenue")
        if latest is not None and prev is not None and prev > 0:
            yoy = (latest - prev) / prev * 100
            if yoy > 20:
                bullish += 0.05
                bull_reasons.append(f"年化营收同比 +{yoy:.1f}%")
            elif yoy < -20:
                bearish += 0.05
                bear_reasons.append(f"年化营收同比 {yoy:.1f}%")

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
        if score_diff > SIGNAL_BULLISH_STRONG:
            parts.append("多头信号较强")
        elif score_diff > SIGNAL_BULLISH_WEAK:
            parts.append("短期偏多")
        elif score_diff < SIGNAL_BEARISH_STRONG:
            parts.append("空头信号较强")
        elif score_diff < SIGNAL_BEARISH_WEAK:
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
