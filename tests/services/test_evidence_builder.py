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
