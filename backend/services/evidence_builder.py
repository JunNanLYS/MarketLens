"""证据构建器（异步版）——聚合各类数据为 AI 分析提供输入。"""

import json
from contextlib import suppress

from backend.config import get_config


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
    def _derive_finance_yoy(rows: list[dict]) -> dict | None:
        """对 ``rows``（按 collected_at DESC 排序的最近 N 期）做 YoY/差值派生。

        派生字段：
        - ``revenue_yoy`` / ``net_profit_yoy`` / ``eps_yoy``: 百分比（最新 vs 前一期）
        - ``roe_change``: ROE 绝对差值
        - ``prev_*``: 前一期原值（向后兼容）
        - ``history``: 多期列表（按时间从旧到新）

        返回 latest 字典（已附加派生字段）；若 ``rows`` 为空则返回 ``None``。
        """
        if not rows:
            return None
        latest = dict(rows[0])
        if len(rows) >= 2:
            prev = dict(rows[1])
            for key in ("revenue", "net_profit", "eps"):
                curr_val = latest.get(key)
                prev_val = prev.get(key)
                if curr_val is not None and prev_val is not None and prev_val != 0:
                    latest[f"{key}_yoy"] = round((curr_val - prev_val) / abs(prev_val) * 100, 2)
                else:
                    latest[f"{key}_yoy"] = None
            if latest.get("roe") is not None and prev.get("roe") is not None:
                latest["roe_change"] = round(latest["roe"] - prev["roe"], 2)
            else:
                latest["roe_change"] = None
            latest["prev_revenue"] = prev.get("revenue")
            latest["prev_net_profit"] = prev.get("net_profit")
            latest["prev_eps"] = prev.get("eps")
            latest["prev_roe"] = prev.get("roe")
        else:
            for key in ("revenue", "net_profit", "eps"):
                latest[f"{key}_yoy"] = None
            latest["roe_change"] = None
        latest["history"] = [dict(r) for r in reversed(rows)]
        return latest

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
            dividends = await EvidenceBuilder._build_dividends(conn, symbol)
            shareholders = await EvidenceBuilder._build_shareholders(conn, symbol)
            forecasts = await EvidenceBuilder._build_profit_forecasts(conn, symbol)
            sector_ctx = await EvidenceBuilder._build_sector_context(conn, symbol)
            # 美股财务：仅 us 前缀的标的才查询（避免浪费 IO）
            us_finance = (
                await EvidenceBuilder._build_us_finance(conn, symbol)
                if symbol.startswith("us")
                else None
            )

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
            if dividends:
                data_sources.append({"type": "dividend", "source": dividends.get("source", ""), "collected_at": ""})
            if shareholders:
                data_sources.append({"type": "shareholder", "source": shareholders.get("source", ""), "collected_at": ""})
            if forecasts:
                data_sources.append({"type": "forecast", "source": forecasts.get("source", ""), "collected_at": ""})
            if sector_ctx:
                data_sources.append({"type": "sector_context", "source": sector_ctx.get("source", ""), "collected_at": sector_ctx.get("collected_at", "")})
            if us_finance:
                data_sources.append({"type": "us_finance", "source": us_finance.get("source", ""), "collected_at": us_finance.get("collected_at", "")})

            return {
                "symbol": symbol,
                "quote": quote,
                "kline": klines,
                "fund_flows": fund_flows,
                "finance": finance,
                "news": news,
                "technical": technical,
                "dividends": dividends,
                "shareholders": shareholders,
                "forecasts": forecasts,
                "sector_context": sector_ctx,
                "us_finance": us_finance,
                "data_sources": data_sources,
            }
        finally:
            if close_conn:
                with suppress(Exception):
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

            # dividends：取每标的最近 4 次分红（按 ex_date DESC）
            cursor = await conn.execute(
                f"""SELECT * FROM dividends
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, ex_date DESC""",
                params,
            )
            divs_by_symbol: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                divs_by_symbol.setdefault(sym, []).append(r)
                if len(divs_by_symbol[sym]) >= 4:
                    del divs_by_symbol[sym][4:]

            # shareholders：取每标的最新一期前 10 名（按 report_period DESC, rank ASC）
            shr_by_symbol: dict[str, dict] = {}
            cursor = await conn.execute(
                f"""SELECT * FROM shareholders
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, report_period DESC, rank ASC""",
                params,
            )
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                bucket = shr_by_symbol.get(sym)
                if bucket is None:
                    bucket = {
                        "top_shareholders": [],
                        "latest_period": r["report_period"],
                        "source": r.get("source"),
                    }
                    shr_by_symbol[sym] = bucket
                if r["report_period"] != bucket["latest_period"]:
                    # 已超过该标的的最新一期，停止
                    continue
                if len(bucket["top_shareholders"]) < 10:
                    bucket["top_shareholders"].append(r)
            # 股东人数趋势：取每标的最近 8 个报告期
            cursor = await conn.execute(
                f"""SELECT * FROM shareholder_count_history
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, report_date DESC""",
                params,
            )
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                bucket = shr_by_symbol.setdefault(
                    sym,
                    {"top_shareholders": [], "source": r.get("source")},
                )
                bucket.setdefault("holder_count_trend", [])
                if len(bucket["holder_count_trend"]) < 8:
                    bucket["holder_count_trend"].append(r)
                if not bucket.get("source"):
                    bucket["source"] = r.get("source")
            # 清理临时字段 latest_period
            for bucket in shr_by_symbol.values():
                bucket.pop("latest_period", None)

            # profit_forecasts：取每标的最近 4 个报告期
            cursor = await conn.execute(
                f"""SELECT * FROM profit_forecasts
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, report_period DESC""",
                params,
            )
            fcsts_by_symbol: dict[str, list[dict]] = {}
            for row in await cursor.fetchall():
                r = dict(row)
                sym = r["symbol"]
                fcsts_by_symbol.setdefault(sym, []).append(r)
                if len(fcsts_by_symbol[sym]) >= 4:
                    del fcsts_by_symbol[sym][4:]

            # news：批量拉取 7 天窗口内新闻，Python 端按 related_symbols 聚合。
            # 替代原来的 N 次单标的 json_each 查询，性能提升 N 倍。
            # LIMIT 5000 防止全表扫：单标的 evidence 包不需要 7 天内所有新闻。
            cursor = await conn.execute(
                """SELECT * FROM news_items
                   WHERE published_at >= datetime("now", "-7 days")
                   ORDER BY published_at DESC
                   LIMIT 5000""",
            )
            all_news_rows: list[dict] = [dict(r) for r in await cursor.fetchall()]
            news_by_symbol: dict[str, list[dict]] = {sym: [] for sym in symbols}
            for row in all_news_rows:
                related_raw = row.get("related_symbols")
                if not related_raw:
                    continue
                try:
                    related = json.loads(related_raw) if isinstance(related_raw, str) else related_raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(related, list):
                    continue
                for sym in related:
                    bucket = news_by_symbol.get(sym)
                    if bucket is not None and len(bucket) < 100:
                        bucket.append(row)

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
                # 财务：复用单标的 _derive_finance_yoy 保证语义一致
                finance = EvidenceBuilder._derive_finance_yoy(fin_by_symbol.get(symbol, []))
                # dividends：取最近 4 期（按 ex_date DESC 已是当前顺序）
                divs = divs_by_symbol.get(symbol, [])
                dividends = None
                if divs:
                    dividends = {
                        "history": divs,
                        "latest_cash_dividend": divs[0]["cash_dividend"],
                        "latest_ex_date": divs[0]["ex_date"],
                        "source": divs[0].get("source"),
                    }
                # shareholders：来自 shr_by_symbol；组装同单标的版对齐
                shr_bucket = shr_by_symbol.get(symbol)
                shareholders = None
                if shr_bucket and (shr_bucket.get("top_shareholders") or shr_bucket.get("holder_count_trend")):
                    shareholders = {
                        "top_shareholders": shr_bucket.get("top_shareholders", []),
                        "holder_count_trend": shr_bucket.get("holder_count_trend", []),
                        "source": shr_bucket.get("source"),
                    }
                # profit_forecasts：取最近 4 期
                fcsts = fcsts_by_symbol.get(symbol, [])
                forecasts = None
                if fcsts:
                    forecasts = {
                        "history": fcsts,
                        "latest": fcsts[0],
                        "source": fcsts[0].get("source"),
                    }

                # news from pre-aggregated dict
                news_rows = news_by_symbol.get(symbol, [])
                news = None
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
                if dividends:
                    data_sources.append({"type": "dividend", "source": dividends.get("source", ""), "collected_at": ""})
                if shareholders:
                    data_sources.append({"type": "shareholder", "source": shareholders.get("source", ""), "collected_at": ""})
                if forecasts:
                    data_sources.append({"type": "forecast", "source": forecasts.get("source", ""), "collected_at": ""})

                result[symbol] = {
                    "symbol": symbol,
                    "quote": quote,
                    "kline": klines,
                    "fund_flows": flows,
                    "finance": finance,
                    "news": news,
                    "technical": tech_map.get(symbol),
                    "dividends": dividends,
                    "shareholders": shareholders,
                    "forecasts": forecasts,
                    "data_sources": data_sources,
                }
            return result
        finally:
            with suppress(Exception):
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
        """多期财务 + YoY 派生指标。

        取最近 ``finance_limit`` 期（默认 4）财务数据，派生：
        - ``revenue_yoy``: 营收同比（最新 vs 前一期，单位 %）
        - ``net_profit_yoy``: 净利润同比
        - ``eps_yoy``: EPS 同比
        - ``roe_change``: ROE 差值（绝对值，单位百分点）
        - ``history``: 全部期次的列表（按时间从旧到新）
        """
        limits = EvidenceBuilder._evidence_limits()
        cursor = await conn.execute(
            """SELECT * FROM financial_reports WHERE symbol = ?
               ORDER BY collected_at DESC LIMIT ?""",
            (symbol, limits["finance_limit"]),
        )
        rows = await cursor.fetchall()
        return EvidenceBuilder._derive_finance_yoy([dict(r) for r in rows])

    @staticmethod
    async def _build_dividends(conn, symbol: str) -> dict | None:
        """查询最近 4 次分红历史 + 最新一次派息。"""
        cursor = await conn.execute(
            """SELECT * FROM dividends WHERE symbol = ?
               ORDER BY ex_date DESC LIMIT 4""",
            (symbol,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return {
            "history": [dict(r) for r in rows],
            "latest_cash_dividend": rows[0]["cash_dividend"] if rows else None,
            "latest_ex_date": rows[0]["ex_date"] if rows else None,
            "source": rows[0]["source"] if rows else None,
        }

    @staticmethod
    async def _build_shareholders(conn, symbol: str) -> dict | None:
        """查询最新一期十大股东 + 股东人数趋势。"""
        # 十大股东（按报告期降序、排名升序，取最新一期前 10 名）
        cursor = await conn.execute(
            """SELECT * FROM shareholders WHERE symbol = ?
               ORDER BY report_period DESC, rank ASC LIMIT 10""",
            (symbol,),
        )
        top_rows = await cursor.fetchall()
        # 股东人数历史（最近 8 个报告期）
        cursor = await conn.execute(
            """SELECT * FROM shareholder_count_history WHERE symbol = ?
               ORDER BY report_date DESC LIMIT 8""",
            (symbol,),
        )
        count_rows = await cursor.fetchall()
        if not top_rows and not count_rows:
            return None
        return {
            "top_shareholders": [dict(r) for r in top_rows],
            "holder_count_trend": [dict(r) for r in count_rows],
            "source": (
                top_rows[0]["source"] if top_rows
                else (count_rows[0]["source"] if count_rows else None)
            ),
        }

    @staticmethod
    async def _build_profit_forecasts(conn, symbol: str) -> dict | None:
        """查询最近 4 个报告期的业绩预告。"""
        cursor = await conn.execute(
            """SELECT * FROM profit_forecasts WHERE symbol = ?
               ORDER BY report_period DESC LIMIT 4""",
            (symbol,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return {
            "history": [dict(r) for r in rows],
            "latest": dict(rows[0]) if rows else None,
            "source": rows[0]["source"] if rows else None,
        }

    @staticmethod
    async def _build_sector_context(conn, symbol: str) -> dict | None:
        """查询板块背景（行业/概念涨幅榜 Top 5 + 资金流入 Top 5）。

        不依赖具体 symbol（板块是全市场级别），但保留 symbol 参数以保持
        模板一致性。AI 报告引用大盘背景，让"今天哪些板块涨/跌"成为依据。
        """
        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type IN ('industry', 'concept', 'fund_flow')
               ORDER BY change_pct DESC LIMIT 5"""
        )
        top_gainers = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type IN ('industry', 'concept', 'fund_flow')
               ORDER BY change_pct ASC LIMIT 5"""
        )
        top_losers = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            """SELECT * FROM sector_daily_quote
               WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
               AND sector_type = 'fund_flow'
               ORDER BY main_net_inflow DESC NULLS LAST LIMIT 5"""
        )
        top_fund_inflow = [dict(r) for r in await cursor.fetchall()]

        if not top_gainers and not top_losers and not top_fund_inflow:
            return None

        source = top_gainers[0].get("source") if top_gainers else (
            top_losers[0].get("source") if top_losers else (
                top_fund_inflow[0].get("source") if top_fund_inflow else None
            )
        )
        collected_at = top_gainers[0].get("collected_at") if top_gainers else None

        return {
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "top_fund_inflow": top_fund_inflow,
            "source": source,
            "collected_at": collected_at,
        }

    @staticmethod
    async def _build_us_finance(conn, symbol: str) -> dict | None:
        """查询美股财务（us_financials 表，period_type=annual 最新 4 期）。"""
        cursor = await conn.execute(
            """SELECT * FROM us_financials WHERE symbol = ?
               AND period_type = 'annual'
               ORDER BY end_date DESC LIMIT 4""",
            (symbol,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        annual = [dict(r) for r in rows]

        cursor = await conn.execute(
            """SELECT * FROM us_financials WHERE symbol = ?
               AND period_type = 'quarter'
               ORDER BY end_date DESC LIMIT 4""",
            (symbol,),
        )
        quarterly = [dict(r) for r in await cursor.fetchall()]

        # 派生 YoY 增长率（最近一年 vs 去年）
        yoy = {}
        if len(annual) >= 2:
            curr = annual[0]
            prev = annual[1]
            for k in ("revenue", "net_income", "operating_income", "ebitda", "basic_eps"):
                c, p = curr.get(k), prev.get(k)
                if c is not None and p is not None and p != 0:
                    yoy[f"{k}_yoy"] = round((c - p) / p * 100, 2)

        return {
            "annual": annual,
            "quarterly": quarterly,
            "yoy": yoy,
            "currency": annual[0].get("currency"),
            "source": annual[0].get("source"),
            "collected_at": annual[0].get("collected_at"),
        }

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

