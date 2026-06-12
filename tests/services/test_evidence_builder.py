import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services.evidence_builder import EvidenceBuilder
from backend.storage.database import aget_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture
def tmp_db(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    set_db_path(db_path)
    init_db(db_path)
    try:
        yield Path(db_path)
    finally:
        set_db_path(None)


async def _insert_quote(conn, symbol: str = "hk00700", price: float = 380.0) -> None:
    await conn.execute(
        """INSERT INTO market_quotes (symbol, price, change, change_pct, volume, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol,
            price,
            5.0,
            1.33,
            1000000,
            "westock",
            datetime.now(timezone.utc).isoformat(),
        ),
    )


async def _insert_kline(conn, symbol: str = "hk00700", days: int = 60) -> None:
    base_date = datetime(2026, 5, 31)
    for i in range(days):
        date = (base_date - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        close = 350.0 + i * 0.5
        await conn.execute(
            """INSERT INTO kline_daily (symbol, date, open, high, low, close, volume, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                date,
                close - 1,
                close + 2,
                close - 2,
                close,
                500000 + i * 1000,
                "westock",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


async def _insert_fund_flows(conn, symbol: str = "hk00700", days: int = 5) -> None:
    base_date = datetime(2026, 5, 31)
    for i in range(days):
        date = (base_date - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        await conn.execute(
            """INSERT INTO fund_flows (symbol, date, main_net_inflow, net_inflow_ratio, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                date,
                1000000.0 + i * 100000,
                2.5,
                "westock",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


async def _insert_finance(conn, symbol: str = "hk00700") -> None:
    await conn.execute(
        """INSERT INTO financial_reports
           (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
            eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol,
            "2026Q1",
            150000000000,
            8.5,
            40000000000,
            5.2,
            4.2,
            18.5,
            45.0,
            52.0,
            26.7,
            "westock",
            datetime.now(timezone.utc).isoformat(),
        ),
    )


async def _insert_news(conn, symbol: str = "hk00700") -> None:
    now = datetime.now(timezone.utc)
    for i, sentiment in enumerate(
        ["positive", "positive", "positive", "negative", "neutral"]
    ):
        await conn.execute(
            """INSERT INTO news_items (title, source, url, sentiment, importance, related_symbols, published_at, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"新闻 {i + 1}",
                "sina_rss",
                f"https://example.com/news/{i}",
                sentiment,
                "normal",
                json.dumps([symbol]),
                (now - timedelta(days=i)).isoformat(),
                now.isoformat(),
            ),
        )


async def _insert_technical(conn, symbol: str = "hk00700") -> None:
    now = datetime.now(timezone.utc)
    await conn.execute(
        """INSERT INTO technical_indicators
           (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
            rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol,
            "2026-05-30",
            375.0,
            372.0,
            368.0,
            360.0,
            2.5,
            1.8,
            0.7,
            55.0,
            52.0,
            390.0,
            375.0,
            360.0,
            "westock",
            now.isoformat(),
        ),
    )
    await conn.execute(
        """INSERT INTO technical_indicators
           (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
            rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol,
            "2026-05-29",
            374.0,
            371.0,
            367.0,
            359.0,
            1.5,
            1.6,
            -0.1,
            54.0,
            51.0,
            389.0,
            374.0,
            359.0,
            "westock",
            now.isoformat(),
        ),
    )


class TestEvidenceBuilderFull:
    """证据包完整（有全部数据类型）。"""

    async def test_full_evidence(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_quote(conn)
            await _insert_kline(conn)
            await _insert_fund_flows(conn)
            await _insert_finance(conn)
            await _insert_news(conn)
            await _insert_technical(conn)

        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["symbol"] == "hk00700"
        assert evidence["quote"] is not None
        assert evidence["quote"]["price"] == 380.0
        assert len(evidence["kline"]) == 60
        assert len(evidence["fund_flows"]) == 5
        assert evidence["finance"] is not None
        assert evidence["finance"]["roe"] == 18.5
        assert evidence["news"] is not None
        assert evidence["news"]["total_count"] == 5
        assert evidence["news"]["positive_count"] == 3
        assert evidence["news"]["negative_count"] == 1
        assert evidence["news"]["neutral_count"] == 1
        assert evidence["technical"] is not None
        assert evidence["technical"]["rsi14"] == 52.0
        assert evidence["technical"]["prev_macd_histogram"] == -0.1
        assert len(evidence["data_sources"]) > 0


class TestEvidenceBuilderPartial:
    """证据不足（仅有部分数据）。"""

    async def test_partial_evidence_only_quote(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_quote(conn)

        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["quote"] is not None
        assert evidence["kline"] == []
        assert evidence["fund_flows"] == []
        assert evidence["finance"] is None
        assert evidence["news"] is None
        assert evidence["technical"] is None

    async def test_partial_evidence_quote_and_kline(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_quote(conn)
            await _insert_kline(conn, days=10)

        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["quote"] is not None
        assert len(evidence["kline"]) == 10
        assert evidence["finance"] is None


class TestEvidenceBuilderEmpty:
    """无数据时返回空证据包。"""

    async def test_no_data(self, tmp_db: Path) -> None:
        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["symbol"] == "hk00700"
        assert evidence["quote"] is None
        assert evidence["kline"] == []
        assert evidence["fund_flows"] == []
        assert evidence["finance"] is None
        assert evidence["news"] is None
        assert evidence["technical"] is None
        assert evidence["data_sources"] == []


class TestEvidenceBuilderKlineMA:
    """K 线 MA 计算正确。"""

    async def test_ma_calculation(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_kline(conn, days=60)

        evidence = await EvidenceBuilder.build("hk00700")
        kline = evidence["kline"]

        assert len(kline) == 60
        last_item = kline[-1]
        assert last_item["ma5"] is not None
        assert last_item["ma10"] is not None
        assert last_item["ma20"] is not None
        assert last_item["ma60"] is not None

        first_item = kline[0]
        assert first_item.get("ma5") is None
        assert first_item.get("ma60") is None

    async def test_ma5_value(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_kline(conn, days=10)

        evidence = await EvidenceBuilder.build("hk00700")
        kline = evidence["kline"]
        last5 = [item["close"] for item in kline[-5:]]
        expected_ma5 = round(sum(last5) / 5, 4)
        assert kline[-1]["ma5"] == expected_ma5


class TestEvidenceBuilderNewsStats:
    """新闻统计正确。"""

    async def test_news_statistics(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_news(conn)

        evidence = await EvidenceBuilder.build("hk00700")
        news = evidence["news"]

        assert news is not None
        assert news["total_count"] == 5
        assert news["positive_count"] == 3
        assert news["negative_count"] == 1
        assert news["neutral_count"] == 1

    async def test_no_matching_news(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await conn.execute(
                """INSERT INTO news_items (title, source, url, sentiment, importance, related_symbols, published_at, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "无关新闻",
                    "sina_rss",
                    "https://example.com/other",
                    "neutral",
                    "normal",
                    json.dumps(["sh600519"]),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        evidence = await EvidenceBuilder.build("hk00700")
        assert evidence["news"] is None


# ---------------------------------------------------------------------------
# 第 2 阶段新增：3 个新维度 + 财务多期 YoY 派生
# ---------------------------------------------------------------------------


async def _insert_dividends(conn, symbol: str = "hk00700", count: int = 4) -> None:
    """插入 N 条分红记录（ex_date 从 2026-Q1 ~ 2025-Q4 倒序）。"""
    base_dates = ["2026-04-15", "2025-04-20", "2024-04-18", "2023-04-22"]
    cash_values = [10.5, 8.2, 7.0, 6.5]
    for i in range(count):
        await conn.execute(
            """INSERT INTO dividends
               (symbol, ex_date, cash_dividend, share_bonus, record_date, announce_date,
                dividend_year, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                base_dates[i],
                cash_values[i],
                0.0,
                base_dates[i],
                base_dates[i],
                2026 - i,
                "westock",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


async def _insert_profit_forecasts(
    conn, symbol: str = "hk00700", count: int = 4
) -> None:
    """插入 N 条业绩预告。"""
    periods = ["2026Q1", "2025Q4", "2025Q3", "2025Q2"]
    for i in range(count):
        await conn.execute(
            """INSERT INTO profit_forecasts
               (symbol, report_period, forecast_type, profit_lower, profit_upper,
                change_lower, change_upper, summary, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                periods[i],
                "pre_increase",
                38000000000,
                42000000000,
                8.0,
                12.0,
                "预计净利润同比增长",
                "westock",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


async def _insert_shareholders(conn, symbol: str = "hk00700") -> None:
    """插入十大股东 + 股东人数历史。"""
    now = datetime.now(timezone.utc).isoformat()
    # 十大股东：最新一期 2026Q1，10 个股东
    for rank in range(1, 11):
        await conn.execute(
            """INSERT INTO shareholders
               (symbol, report_period, rank, name, shares, ratio, change_amount,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                "2026Q1",
                rank,
                f"股东{rank}",
                10000000 - rank * 100000,
                0.5 - rank * 0.01,
                -rank * 1000.0,
                "westock",
                now,
            ),
        )
    # 股东人数历史：8 个报告期
    base_dates = [
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
        "2025-06-30",
        "2025-03-31",
        "2024-12-31",
        "2024-09-30",
        "2024-06-30",
    ]
    holders = [25000, 24000, 23500, 23000, 22500, 22000, 21500, 21000]
    for i, d in enumerate(base_dates):
        await conn.execute(
            """INSERT INTO shareholder_count_history
               (symbol, report_date, total_holders, avg_shares, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (symbol, d, holders[i], 1000.0, "westock", now),
        )


async def _insert_finance_multi(
    conn, symbol: str = "hk00700", periods: int = 2
) -> None:
    """插入 N 期财务（默认 2 期：curr=200, prev=100 → yoy=100）。"""
    now = datetime.now(timezone.utc).isoformat()
    base_data = [
        (200, 50, 2.0, 18.0),  # 最新期
        (100, 25, 1.0, 15.0),  # 前一期
        (80, 20, 0.8, 14.0),  # 更早
        (60, 15, 0.6, 13.0),  # 最旧
    ]
    for i in range(periods):
        revenue, net_profit, eps, roe = base_data[i]
        await conn.execute(
            """INSERT INTO financial_reports
               (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
                eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                f"2026Q{i + 1}",
                revenue,
                0.0,
                net_profit,
                0.0,
                eps,
                roe,
                45.0,
                52.0,
                26.7,
                "westock",
                now,
            ),
        )


class TestEvidenceBuilderDividends:
    """_build_dividends：4 期历史 + latest 字段。"""

    async def test_dividends_4_periods(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_dividends(conn, count=4)

        async with aget_db() as conn:
            result = await EvidenceBuilder._build_dividends(conn, "hk00700")

        assert result is not None
        assert len(result["history"]) == 4
        # history 按 ex_date DESC 排序：2026-04-15 排第一
        assert result["history"][0]["ex_date"] == "2026-04-15"
        assert result["history"][-1]["ex_date"] == "2023-04-22"
        assert result["latest_cash_dividend"] == 10.5
        assert result["latest_ex_date"] == "2026-04-15"
        assert result["source"] == "westock"

    async def test_dividends_empty(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            result = await EvidenceBuilder._build_dividends(conn, "hk00700")
        assert result is None


class TestEvidenceBuilderShareholders:
    """_build_shareholders：双表（top + trend）。"""

    async def test_shareholders_dual_table(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_shareholders(conn)

        async with aget_db() as conn:
            result = await EvidenceBuilder._build_shareholders(conn, "hk00700")

        assert result is not None
        assert len(result["top_shareholders"]) == 10
        # top_shareholders 按 rank 升序
        assert result["top_shareholders"][0]["rank"] == 1
        assert result["top_shareholders"][9]["rank"] == 10
        assert len(result["holder_count_trend"]) == 8
        # holder_count_trend 按 report_date DESC
        assert result["holder_count_trend"][0]["report_date"] == "2026-03-31"
        assert result["source"] == "westock"

    async def test_shareholders_empty(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            result = await EvidenceBuilder._build_shareholders(conn, "hk00700")
        assert result is None


class TestEvidenceBuilderProfitForecasts:
    """_build_profit_forecasts：4 期 + latest 字段。"""

    async def test_forecasts_4_periods(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_profit_forecasts(conn, count=4)

        async with aget_db() as conn:
            result = await EvidenceBuilder._build_profit_forecasts(conn, "hk00700")

        assert result is not None
        assert len(result["history"]) == 4
        # history 按 report_period DESC
        assert result["history"][0]["report_period"] == "2026Q1"
        assert result["history"][-1]["report_period"] == "2025Q2"
        assert result["latest"]["report_period"] == "2026Q1"
        assert result["latest"]["profit_upper"] == 42000000000
        assert result["source"] == "westock"

    async def test_forecasts_empty(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            result = await EvidenceBuilder._build_profit_forecasts(conn, "hk00700")
        assert result is None


class TestEvidenceBuilderFinanceYoY:
    """_build_finance YoY 派生。"""

    async def test_finance_yoy_derivation(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_finance_multi(conn, periods=2)

        async with aget_db() as conn:
            result = await EvidenceBuilder._build_finance(conn, "hk00700")

        assert result is not None
        # curr=200, prev=100 → yoy=100%
        assert result["revenue_yoy"] == 100.0
        # curr=50, prev=25 → yoy=100%
        assert result["net_profit_yoy"] == 100.0
        # curr=2.0, prev=1.0 → yoy=100%
        assert result["eps_yoy"] == 100.0
        # curr_roe=18.0, prev_roe=15.0 → change=3.0
        assert result["roe_change"] == 3.0
        # 向后兼容字段
        assert result["prev_revenue"] == 100
        assert result["prev_net_profit"] == 25
        assert result["prev_eps"] == 1.0
        assert result["prev_roe"] == 15.0
        # history 至少含 2 期
        assert len(result["history"]) == 2

    async def test_finance_yoy_single_period(self, tmp_db: Path) -> None:
        """仅有 1 期时所有 YoY/roe_change 字段应为 None。"""
        async with aget_db() as conn:
            await _insert_finance_multi(conn, periods=1)

        async with aget_db() as conn:
            result = await EvidenceBuilder._build_finance(conn, "hk00700")

        assert result is not None
        assert result["revenue_yoy"] is None
        assert result["net_profit_yoy"] is None
        assert result["eps_yoy"] is None
        assert result["roe_change"] is None
        # 单期没有 prev_* 字段
        assert "prev_revenue" not in result
        # history 仍含 1 期
        assert len(result["history"]) == 1


class TestEvidenceBuilderIntegration:
    """build() 主流程：3 个新维度都返回。"""

    async def test_build_includes_three_new_dimensions(self, tmp_db: Path) -> None:
        async with aget_db() as conn:
            await _insert_dividends(conn, count=4)
            await _insert_shareholders(conn)
            await _insert_profit_forecasts(conn, count=4)
            await _insert_finance_multi(conn, periods=2)

        evidence = await EvidenceBuilder.build("hk00700")

        # 3 个新 key 都存在
        assert "dividends" in evidence
        assert "shareholders" in evidence
        assert "forecasts" in evidence
        # 内容非 None
        assert evidence["dividends"] is not None
        assert evidence["shareholders"] is not None
        assert evidence["forecasts"] is not None
        # data_sources 包含 3 个新类型
        types = {item["type"] for item in evidence["data_sources"]}
        assert "dividend" in types
        assert "shareholder" in types
        assert "forecast" in types
        # finance 仍有 YoY 派生
        assert evidence["finance"]["revenue_yoy"] == 100.0


# ---------------------------------------------------------------------------
# 第 12 批: 边界条件 + 错误路径补充测试
# ---------------------------------------------------------------------------


class TestEvidenceBuilderSectorContextOnly:
    """仅 sector_context 时也能正确装配, 不应触发 key 缺失。"""

    async def test_sector_context_only_assembles_correctly(
        self, tmp_db: Path
    ) -> None:
        """仅有板块数据时, evidence 包结构完整, 其他字段为 None / 空。"""
        now = datetime.now(timezone.utc).isoformat()
        async with aget_db() as conn:
            # 插入最新日期的板块涨幅榜（领涨 + 领跌 至少各 1 条）
            await conn.execute(
                """INSERT INTO sector_daily_quote
                   (name, date, sector_type, symbol, change_pct, main_net_inflow,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("半导体", "2026-05-31", "industry", None, 5.2, 1e9, "westock", now),
            )
            await conn.execute(
                """INSERT INTO sector_daily_quote
                   (name, date, sector_type, symbol, change_pct, main_net_inflow,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("房地产", "2026-05-31", "industry", None, -3.8, -5e8, "westock", now),
            )

        evidence = await EvidenceBuilder.build("hk00700")

        # sector_context 应非 None, 包含 top_gainers 和 top_losers
        assert evidence["sector_context"] is not None
        assert len(evidence["sector_context"]["top_gainers"]) >= 1
        assert len(evidence["sector_context"]["top_losers"]) >= 1
        assert evidence["sector_context"]["top_gainers"][0]["name"] == "半导体"
        assert evidence["sector_context"]["top_losers"][0]["name"] == "房地产"

        # 其他维度均为空/None, 但 key 齐全
        assert evidence["quote"] is None
        assert evidence["kline"] == []
        assert evidence["fund_flows"] == []
        assert evidence["finance"] is None
        assert evidence["news"] is None
        assert evidence["technical"] is None
        assert evidence["dividends"] is None
        assert evidence["shareholders"] is None
        assert evidence["forecasts"] is None

        # data_sources 应包含 sector_context 条目
        types = {item["type"] for item in evidence["data_sources"]}
        assert "sector_context" in types


class TestEvidenceBuilderFinanceSignHintRoundtrip:
    """sign_hint 标签在 evidence 包与 _derive_finance_yoy 之间的正确传递。"""

    async def test_loss_narrowing_sign_propagated_to_evidence(
        self, tmp_db: Path
    ) -> None:
        """prev<0 curr<0 且 |curr| < |prev| → loss_narrowing 标签传递到 evidence。

        CLAUDE.md 优先级 1: 资金主线 + AI 价值 —— AI 应把"亏损收窄"识别为
        看多信号,所以 evidence 包内 sign_hint 必须可被 AIAnalyzer 正确读取。
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aget_db() as conn:
            # 最新期：净利润 -50 (亏损 50)
            await conn.execute(
                """INSERT INTO financial_reports
                   (symbol, report_period, revenue, net_profit, eps, roe,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hk00700", "2026Q1", 1000, -50, -0.5, -2.0, "westock", now),
            )
            # 前一期：净利润 -200 (亏损 200, 收窄)
            await conn.execute(
                """INSERT INTO financial_reports
                   (symbol, report_period, revenue, net_profit, eps, roe,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hk00700", "2025Q4", 800, -200, -2.0, -8.0, "westock", now),
            )

        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["finance"] is not None
        # 符号语义标签应传递为 loss_narrowing
        assert evidence["finance"]["net_profit_yoy_sign"] == "loss_narrowing"
        # 营收 yoy 派生 (1000-800)/abs(800)*100 = 25.0
        assert evidence["finance"]["revenue_yoy"] == 25.0
        # 净利润 yoy (-50 - -200) / 200 * 100 = 75.0
        assert evidence["finance"]["net_profit_yoy"] == 75.0

        # 把 evidence 喂给 AIAnalyzer,验证 sign hint 触发看多。
        # 注入最小 quote 以绕过 has_any_evidence 判定（finance 不在其中）。
        from backend.services.ai_analyzer import AIAnalyzer

        evidence_for_ai = dict(evidence)
        evidence_for_ai["quote"] = {"price": 10.0, "source": "test", "collected_at": now}
        result = AIAnalyzer.analyze(evidence_for_ai)
        assert any("亏损收窄" in r for r in result["bullish_reasons"]), (
            f"sign=loss_narrowing 未触发看多, 实际 reasons={result['bullish_reasons']}"
        )

    async def test_turnaround_sign_propagated_to_evidence(
        self, tmp_db: Path
    ) -> None:
        """prev<0 curr>0 → turnaround 标签。"""
        now = datetime.now(timezone.utc).isoformat()
        async with aget_db() as conn:
            # 最新期：扭亏为盈 +100
            await conn.execute(
                """INSERT INTO financial_reports
                   (symbol, report_period, revenue, net_profit, eps, roe,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hk00700", "2026Q1", 1000, 100, 1.0, 5.0, "westock", now),
            )
            # 前一期：亏损 -50
            await conn.execute(
                """INSERT INTO financial_reports
                   (symbol, report_period, revenue, net_profit, eps, roe,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hk00700", "2025Q4", 800, -50, -0.5, -2.0, "westock", now),
            )

        evidence = await EvidenceBuilder.build("hk00700")

        assert evidence["finance"]["net_profit_yoy_sign"] == "turnaround"

        from backend.services.ai_analyzer import AIAnalyzer

        evidence_for_ai = dict(evidence)
        evidence_for_ai["quote"] = {"price": 10.0, "source": "test", "collected_at": now}
        result = AIAnalyzer.analyze(evidence_for_ai)
        assert any("扭亏为盈" in r for r in result["bullish_reasons"])


# ---------------------------------------------------------------------------
# 第 12 批子任务 C: build_multi 累加截断 + news LIMIT 5000 告警
# ---------------------------------------------------------------------------


class TestBuildMultiTruncation:
    """build_multi 累加阶段应在达到上限时立即停止,不留 history 行到内存。

    第 12 轮 ISSUES 复审:
    - bug #3 (MAJOR): ``klines_by_symbol`` / ``flows_by_symbol`` ``continue``
      语句无截断效果, 单标的实际累计全部历史行, 浪费内存 20x。
    - bug #8 (MINOR): ``news_items LIMIT 5000`` 是静默截断,
      违反 CLAUDE.md "No silent caps" 原则。
    """

    async def test_build_multi_klines_truncate_at_60(
        self, tmp_db: Path
    ) -> None:
        """某 symbol 有 120 行 kline, build_multi 应只取 60 行（截断在累加阶段生效）。"""
        now = datetime.now(timezone.utc).isoformat()
        base_date = datetime(2026, 5, 31)
        async with aget_db() as conn:
            for i in range(120):
                date = (base_date - timedelta(days=120 - 1 - i)).strftime("%Y-%m-%d")
                close = 350.0 + i * 0.5
                await conn.execute(
                    """INSERT INTO kline_daily
                       (symbol, date, open, high, low, close, volume, source, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "hk00700",
                        date,
                        close - 1,
                        close + 2,
                        close - 2,
                        close,
                        500000 + i * 1000,
                        "westock",
                        now,
                    ),
                )

        result = await EvidenceBuilder.build_multi(["hk00700"])
        # 累加阶段截断: 60 行上限生效, 不再累计剩余 60 行
        assert len(result["hk00700"]["kline"]) == 60
        # 反转后第 1 行是 date 最早的一行, 第 60 行是 date 最近的一行
        first_date = result["hk00700"]["kline"][0]["date"]
        last_date = result["hk00700"]["kline"][-1]["date"]
        assert first_date < last_date

    async def test_build_multi_flows_truncate_at_5(
        self, tmp_db: Path
    ) -> None:
        """某 symbol 有 20 行 fund_flows, build_multi 应只取 5 行。"""
        now = datetime.now(timezone.utc).isoformat()
        base_date = datetime(2026, 5, 31)
        async with aget_db() as conn:
            for i in range(20):
                date = (base_date - timedelta(days=20 - 1 - i)).strftime("%Y-%m-%d")
                await conn.execute(
                    """INSERT INTO fund_flows
                       (symbol, date, main_net_inflow, net_inflow_ratio,
                        source, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        "hk00700",
                        date,
                        1_000_000.0 + i * 100_000,
                        2.5,
                        "westock",
                        now,
                    ),
                )

        result = await EvidenceBuilder.build_multi(["hk00700"])
        # 累加阶段截断: 5 行上限生效
        assert len(result["hk00700"]["fund_flows"]) == 5

    async def test_build_multi_news_warning_on_truncate(
        self, tmp_db: Path
    ) -> None:
        """5001 条 news 触发 logger.warning（loguru 截断探测）。"""
        from loguru import logger

        now = datetime.now(timezone.utc)
        async with aget_db() as conn:
            for i in range(5001):
                await conn.execute(
                    """INSERT INTO news_items
                       (title, source, url, sentiment, importance,
                        related_symbols, published_at, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"news-{i}",
                        "sina_rss",
                        f"https://example.com/news/{i}",
                        "neutral",
                        "normal",
                        json.dumps(["hk00700"]),
                        (now - timedelta(seconds=i)).isoformat(),
                        now.isoformat(),
                    ),
                )

        # loguru 测试: 临时挂一个 sink 收集 records
        captured: list[dict] = []
        handler_id = logger.add(
            lambda message: captured.append(
                {
                    "level": message.record["level"].name,
                    "message": message.record["message"],
                }
            ),
            level="WARNING",
        )
        try:
            await EvidenceBuilder.build_multi(["hk00700"])
        finally:
            logger.remove(handler_id)

        # 验证 warning 被记录
        warnings = [c for c in captured if c["level"] == "WARNING"]
        assert any("5000" in c["message"] and "news" in c["message"] for c in warnings), (
            f"news LIMIT 5000 截断 warning 未触发, 实际 captured={captured}"
        )

    async def test_build_multi_mixed_symbols_independent_buckets(
        self, tmp_db: Path
    ) -> None:
        """3 个 symbol 各自 bucket 独立, 互不影响截断计数。"""
        now = datetime.now(timezone.utc).isoformat()
        base_date = datetime(2026, 5, 31)
        symbols = ["hk00700", "sh600000", "usAAPL"]
        async with aget_db() as conn:
            for sym in symbols:
                for i in range(70):  # 每个 > 60, 验证截断
                    date = (base_date - timedelta(days=70 - 1 - i)).strftime("%Y-%m-%d")
                    close = 100.0 + i * 0.3
                    await conn.execute(
                        """INSERT INTO kline_daily
                           (symbol, date, open, high, low, close, volume,
                            source, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            sym,
                            date,
                            close - 1,
                            close + 1,
                            close - 1,
                            close,
                            1000 + i,
                            "westock",
                            now,
                        ),
                    )

        result = await EvidenceBuilder.build_multi(symbols)
        # 每个 symbol 的 kline 都应恰好 60 行
        for sym in symbols:
            assert len(result[sym]["kline"]) == 60, (
                f"{sym} kline 长度异常: {len(result[sym]['kline'])}"
            )


# ---------------------------------------------------------------------------
# TestAggregateNews: _aggregate_news 行为测试
# ---------------------------------------------------------------------------


class TestAggregateNews:
    """EvidenceBuilder._aggregate_news 行为测试。"""

    def test_empty_items_returns_none(self) -> None:
        assert EvidenceBuilder._aggregate_news([]) is None

    def test_counts_and_weighted_sums(self) -> None:
        """raw count + weighted sum 同时正确。"""
        items = [
            {"sentiment": "positive", "confidence": 0.9, "sectors": '["银行"]'},
            {"sentiment": "positive", "confidence": 0.7, "sectors": '["银行"]'},
            {"sentiment": "negative", "confidence": 0.6, "sectors": '["石油"]'},
            {"sentiment": "neutral", "confidence": 0.3, "sectors": None},
        ]
        r = EvidenceBuilder._aggregate_news(items)
        assert r["total_count"] == 4
        assert r["positive_count"] == 2
        assert r["negative_count"] == 1
        assert r["neutral_count"] == 1
        # positive_weighted: 0.9 + 0.7 = 1.6,四舍五入 1.6
        assert r["positive_weighted"] == 1.6
        assert r["negative_weighted"] == 0.6
        assert r["neutral_weighted"] == 0.3
        # avg_confidence: (0.9+0.7+0.6+0.3)/4 = 0.625
        assert r["avg_confidence"] == 0.625

    def test_sector_exposure_aggregates_and_ranks(self) -> None:
        items = [
            {"sentiment": "positive", "confidence": 0.9, "sectors": '["银行", "地产"]'},
            {"sentiment": "positive", "confidence": 0.8, "sectors": '["银行"]'},
            {"sentiment": "negative", "confidence": 0.7, "sectors": '["石油"]'},
        ]
        r = EvidenceBuilder._aggregate_news(items)
        sectors = {s["sector"]: s for s in r["sector_exposure"]}
        assert sectors["银行"]["count"] == 2
        assert sectors["银行"]["positive"] == 2
        # (0.9 + 0.8) / 2 = 0.85
        assert sectors["银行"]["avg_confidence"] == 0.85
        assert sectors["地产"]["count"] == 1
        assert sectors["石油"]["count"] == 1
        assert sectors["石油"]["negative"] == 1
        # 排序：银行 (2) > 地产 (1) = 石油 (1)，并列按字典序
        assert [s["sector"] for s in r["sector_exposure"]] == ["银行", "地产", "石油"]

    def test_backward_compat_null_confidence_treated_as_one(self) -> None:
        """旧数据 confidence=NULL 时按 1.0 计权, weighted = raw count。"""
        items = [
            {"sentiment": "positive", "confidence": None, "sectors": None},
            {"sentiment": "positive", "confidence": None, "sectors": None},
        ]
        r = EvidenceBuilder._aggregate_news(items)
        assert r["positive_count"] == 2
        # None 视为 1.0, 2 * 1.0 = 2.0
        assert r["positive_weighted"] == 2.0
        # 全部 NULL → avg_confidence = None
        assert r["avg_confidence"] is None

    def test_invalid_sectors_json_ignored(self) -> None:
        """sectors 是非法 JSON 时不崩,整条 direction 仍计入。"""
        items = [
            {"sentiment": "positive", "confidence": 0.9, "sectors": "not-json"},
            {"sentiment": "positive", "confidence": 0.9, "sectors": None},
        ]
        r = EvidenceBuilder._aggregate_news(items)
        assert r["positive_count"] == 2
        # sectors 字段全部解析失败 → 空列表
        assert r["sector_exposure"] == []

    def test_sectors_non_list_ignored(self) -> None:
        """sectors 是 JSON 但非 list 时跳过。"""
        items = [{"sentiment": "positive", "confidence": 0.9, "sectors": '"a string"'}]
        r = EvidenceBuilder._aggregate_news(items)
        assert r["positive_count"] == 1
        # 解析出的是 str 而非 list → sector_buckets 不变
        assert r["sector_exposure"] == []
