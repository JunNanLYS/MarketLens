import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.config import get_config
from backend.services.report_service import ReportService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture
async def tmp_db(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    set_db_path(db_path)
    init_db(db_path)
    try:
        yield Path(db_path)
    finally:
        set_db_path(None)


async def _seed_full_data(symbol: str = "hk00700") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled)
               VALUES (?, ?, ?, ?, 1)""",
            (symbol, "腾讯控股", "hk", "stock"),
        )
        conn.execute(
            """INSERT INTO market_quotes (symbol, price, change, change_pct, volume, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (symbol, 380.0, 5.0, 1.33, 1000000, "westock", now),
        )
        base_date = datetime(2026, 5, 31)
        for i in range(60):
            date = (base_date - timedelta(days=59 - i)).strftime("%Y-%m-%d")
            close = 350.0 + i * 0.5
            conn.execute(
                """INSERT INTO kline_daily (symbol, date, open, high, low, close, volume, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, date, close - 1, close + 2, close - 2, close, 500000, "westock", now),
            )
        for i in range(5):
            date = (base_date - timedelta(days=4 - i)).strftime("%Y-%m-%d")
            conn.execute(
                """INSERT INTO fund_flows (symbol, date, main_net_inflow, net_inflow_ratio, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (symbol, date, 1000000.0, 2.5, "westock", now),
            )
        conn.execute(
            """INSERT INTO financial_reports
               (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
                eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, "2026Q1", 150000000000, 8.5, 40000000000, 5.2, 4.2, 18.5, 45.0, 52.0, 26.7, "westock", now),
        )
        for i, sentiment in enumerate(["positive", "positive", "positive", "negative", "neutral"]):
            conn.execute(
                """INSERT INTO news_items (title, source, url, sentiment, importance, related_symbols, published_at, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"新闻 {i + 1}",
                    "sina_rss",
                    f"https://example.com/news/{i}",
                    sentiment,
                    "normal",
                    json.dumps([symbol]),
                    (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(),
                    now,
                ),
            )
        conn.execute(
            """INSERT INTO technical_indicators
               (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
                rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, "2026-05-30", 375.0, 372.0, 368.0, 360.0, 2.5, 1.8, 0.7, 55.0, 52.0, 390.0, 375.0, 360.0, "westock", now),
        )
        conn.execute(
            """INSERT INTO technical_indicators
               (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
                rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, "2026-05-29", 374.0, 371.0, 367.0, 359.0, 1.5, 1.6, -0.1, 54.0, 51.0, 389.0, 374.0, 359.0, "westock", now),
        )


class TestReportServiceGenerate:
    """生成报告成功。"""

    async def test_generate_report(self, tmp_db: Path) -> None:
        await _seed_full_data()
        result = await ReportService.generate_reports(symbols=["hk00700"])
        assert result["generated"] == 1
        assert result["skipped"] == 0

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM ai_reports WHERE symbol = 'hk00700'"
            ).fetchone()
        assert row is not None
        report = dict(row)
        assert report["action"] in ("buy", "sell", "watch", "avoid")
        assert isinstance(report["confidence"], float)
        assert report["risk_level"] in ("low", "medium", "high")


class TestReportServiceIdempotent:
    """报告幂等（同日不重复生成）。"""

    async def test_idempotent(self, tmp_db: Path) -> None:
        await _seed_full_data()
        result1 = await ReportService.generate_reports(symbols=["hk00700"])
        assert result1["generated"] == 1

        result2 = await ReportService.generate_reports(symbols=["hk00700"])
        assert result2["generated"] == 0
        assert result2["skipped"] == 1

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM ai_reports WHERE symbol = 'hk00700'"
            ).fetchone()[0]
        assert count == 1


class TestReportServiceForce:
    """force=True 时覆盖已有报告。"""

    async def test_force_overwrite(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        result = await ReportService.generate_reports(symbols=["hk00700"], force=True)
        assert result["generated"] == 1

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM ai_reports WHERE symbol = 'hk00700'"
            ).fetchone()[0]
        assert count == 1


class TestReportServiceList:
    """查询报告列表。"""

    async def test_list_reports(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        result = ReportService.get_reports()
        assert len(result["items"]) == 1
        assert result["page_info"]["total"] == 1

    async def test_list_with_filter(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        result = ReportService.get_reports(filters={"action": "buy"})
        total = result["page_info"]["total"]
        assert total in (0, 1)


class TestReportServiceLatest:
    """查询最新报告。"""

    async def test_get_latest_report(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        report = ReportService.get_latest_report("hk00700")
        assert report is not None
        assert report["symbol"] == "hk00700"
        assert report["name"] == "腾讯控股"
        assert isinstance(report["bullish_reasons"], list)
        assert isinstance(report["bearish_reasons"], list)
        assert isinstance(report["key_risks"], list)
        assert isinstance(report["data_used"], list)

    async def test_no_report(self, tmp_db: Path) -> None:
        report = ReportService.get_latest_report("hk00001")
        assert report is None


class TestReportServiceHistory:
    """查询历史报告。"""

    async def test_get_history(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        history = ReportService.get_report_history("hk00700")
        assert len(history) == 1
        assert history[0]["symbol"] == "hk00700"

    async def test_no_history(self, tmp_db: Path) -> None:
        history = ReportService.get_report_history("hk00001")
        assert len(history) == 0

    async def test_history_with_date_filter(self, tmp_db: Path) -> None:
        await _seed_full_data()
        await ReportService.generate_reports(symbols=["hk00700"])

        tz_name = get_config().get("scheduler", {}).get("timezone", "Asia/Shanghai")
        today = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        history = ReportService.get_report_history("hk00700", from_date=today, to_date=today)
        assert len(history) == 1

        history = ReportService.get_report_history("hk00700", from_date="2020-01-01", to_date="2020-12-31")
        assert len(history) == 0


class TestReportServiceForceIdempotent:
    """force=True 重复调用不应产生重复行 (依赖 UNIQUE INDEX + INSERT OR IGNORE)。"""

    async def test_force_twice_still_one_row(self, tmp_db: Path) -> None:
        await _seed_full_data()
        result1 = await ReportService.generate_reports(symbols=["hk00700"], force=True)
        result2 = await ReportService.generate_reports(symbols=["hk00700"], force=True)

        assert result1["generated"] == 1
        assert result2["generated"] == 1

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM ai_reports WHERE symbol = 'hk00700'"
            ).fetchone()[0]
        assert count == 1


async def test_generate_reports_run_logs_failure_isolated(tmp_db) -> None:
    """run_logs 写入失败不应掩盖 report 生成结果。"""
    from unittest.mock import patch

    # 先插入一个标的可用于生成
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled) "
            "VALUES (?, ?, ?, ?, 1)",
            ("hk00700", "腾讯控股", "hk", "stock"),
        )

    # 显式传 symbols 跳过 _get_active_symbols 中的 get_db() 调用;
    # 这样 mock 触发的 RuntimeError 只在 run_logs 写入时被抛出,被 try/except 捕获。
    with patch("backend.services.report_service.get_db", side_effect=RuntimeError("disk full")):
        result: dict = await ReportService.generate_reports(symbols=["hk00700"])
    assert "generated" in result
    assert "skipped" in result
    # 实际生成的报告仍应进入 ai_reports
    with get_db() as conn:
        count: int = conn.execute(
            "SELECT COUNT(*) FROM ai_reports"
        ).fetchone()[0]
    assert count >= 1

