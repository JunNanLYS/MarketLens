import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services.evidence_builder import EvidenceBuilder
from backend.storage.database import set_db_path
from backend.storage.schema import init_db


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = str(tmp_path / "test.db")
    set_db_path(db_path)
    init_db(db_path)
    return Path(db_path)


def _insert_quote(conn, symbol: str = "hk00700", price: float = 380.0) -> None:
    conn.execute(
        """INSERT INTO market_quotes (symbol, price, change, change_pct, volume, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, price, 5.0, 1.33, 1000000, "westock", datetime.now(timezone.utc).isoformat()),
    )


def _insert_kline(conn, symbol: str = "hk00700", days: int = 60) -> None:
    base_date = datetime(2026, 5, 31)
    for i in range(days):
        date = (base_date - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        close = 350.0 + i * 0.5
        conn.execute(
            """INSERT INTO kline_daily (symbol, date, open, high, low, close, volume, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, date, close - 1, close + 2, close - 2, close, 500000 + i * 1000, "westock", datetime.now(timezone.utc).isoformat()),
        )


def _insert_fund_flows(conn, symbol: str = "hk00700", days: int = 5) -> None:
    base_date = datetime(2026, 5, 31)
    for i in range(days):
        date = (base_date - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO fund_flows (symbol, date, main_net_inflow, net_inflow_ratio, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (symbol, date, 1000000.0 + i * 100000, 2.5, "westock", datetime.now(timezone.utc).isoformat()),
        )


def _insert_finance(conn, symbol: str = "hk00700") -> None:
    conn.execute(
        """INSERT INTO financial_reports
           (symbol, report_period, revenue, revenue_yoy, net_profit, net_profit_yoy,
            eps, roe, debt_ratio, gross_margin, net_margin, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, "2026Q1", 150000000000, 8.5, 40000000000, 5.2, 4.2, 18.5, 45.0, 52.0, 26.7, "westock", datetime.now(timezone.utc).isoformat()),
    )


def _insert_news(conn, symbol: str = "hk00700") -> None:
    now = datetime.now(timezone.utc)
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
                (now - timedelta(days=i)).isoformat(),
                now.isoformat(),
            ),
        )


def _insert_technical(conn, symbol: str = "hk00700") -> None:
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO technical_indicators
           (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
            rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, "2026-05-30", 375.0, 372.0, 368.0, 360.0, 2.5, 1.8, 0.7, 55.0, 52.0, 390.0, 375.0, 360.0, "westock", now.isoformat()),
    )
    conn.execute(
        """INSERT INTO technical_indicators
           (symbol, date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, macd_histogram,
            rsi6, rsi14, boll_upper, boll_middle, boll_lower, source, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, "2026-05-29", 374.0, 371.0, 367.0, 359.0, 1.5, 1.6, -0.1, 54.0, 51.0, 389.0, 374.0, 359.0, "westock", now.isoformat()),
    )


class TestEvidenceBuilderFull:
    """证据包完整（有全部数据类型）。"""

    def test_full_evidence(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_quote(conn)
            _insert_kline(conn)
            _insert_fund_flows(conn)
            _insert_finance(conn)
            _insert_news(conn)
            _insert_technical(conn)

        evidence = EvidenceBuilder.build("hk00700")

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

    def test_partial_evidence_only_quote(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_quote(conn)

        evidence = EvidenceBuilder.build("hk00700")

        assert evidence["quote"] is not None
        assert evidence["kline"] == []
        assert evidence["fund_flows"] == []
        assert evidence["finance"] is None
        assert evidence["news"] is None
        assert evidence["technical"] is None

    def test_partial_evidence_quote_and_kline(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_quote(conn)
            _insert_kline(conn, days=10)

        evidence = EvidenceBuilder.build("hk00700")

        assert evidence["quote"] is not None
        assert len(evidence["kline"]) == 10
        assert evidence["finance"] is None


class TestEvidenceBuilderEmpty:
    """无数据时返回空证据包。"""

    def test_no_data(self, tmp_db: Path) -> None:
        evidence = EvidenceBuilder.build("hk00700")

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

    def test_ma_calculation(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_kline(conn, days=60)

        evidence = EvidenceBuilder.build("hk00700")
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

    def test_ma5_value(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_kline(conn, days=10)

        evidence = EvidenceBuilder.build("hk00700")
        kline = evidence["kline"]
        last5 = [item["close"] for item in kline[-5:]]
        expected_ma5 = round(sum(last5) / 5, 4)
        assert kline[-1]["ma5"] == expected_ma5


class TestEvidenceBuilderNewsStats:
    """新闻统计正确。"""

    def test_news_statistics(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            _insert_news(conn)

        evidence = EvidenceBuilder.build("hk00700")
        news = evidence["news"]

        assert news is not None
        assert news["total_count"] == 5
        assert news["positive_count"] == 3
        assert news["negative_count"] == 1
        assert news["neutral_count"] == 1

    def test_no_matching_news(self, tmp_db: Path) -> None:
        from backend.storage.database import get_db
        with get_db() as conn:
            conn.execute(
                """INSERT INTO news_items (title, source, url, sentiment, importance, related_symbols, published_at, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("无关新闻", "sina_rss", "https://example.com/other", "neutral", "normal", json.dumps(["sh600519"]), datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
            )

        evidence = EvidenceBuilder.build("hk00700")
        assert evidence["news"] is None
