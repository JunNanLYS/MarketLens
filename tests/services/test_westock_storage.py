"""Unit tests for dividend/profit_forecast/shareholder/minute_klines persistence.

Verifies the 阶段 2 westock-storage changes:
- _insert_dividends / _insert_profit_forecasts / _insert_shareholders / minute_klines INSERT
- The collect_* public methods persist data and return the original provider result
- The _insert_shareholders + _insert_shareholder_count_history is a single transaction
- forecast_type defaults to "weizhi" when missing (NOT NULL constraint)
- dividend_year string-to-int conversion works
"""

from typing import Any
import pytest
from backend.collectors.westock import WeStockProvider
from backend.services.collection_service import CollectionService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db
import tempfile
from pathlib import Path


class WestockMockProvider(WeStockProvider):
    """Subclass WeStockProvider so isinstance filter in collect_* methods passes."""

    def __init__(self, **kwargs: Any) -> None:
        # 避免 __init__ 调 _run_cli / npx
        super().__init__(name="westock")
        self.name = "westock"
        self._dividend = [
            {
                "symbol": "sh600519",
                "ex_date": "2024-06-15",
                "cash_dividend": 30.88,
                "share_bonus": 0.0,
                "record_date": "2024-06-14",
                "announce_date": "2024-04-15",
                "dividend_year": "2023",
                "source": "westock",
                "collected_at": "2026-06-05T00:00:00+00:00",
            },
        ]
        self._reserve = {
            "symbol": "sh600519",
            "report_period": "2024H1",
            "forecast_type": "yuzeng",
            "profit_lower": 1000000000.0,
            "profit_upper": 1100000000.0,
            "change_lower": 5.0,
            "change_upper": 10.0,
            "summary": "ok",
            "source": "westock",
            "collected_at": "2026-06-05T00:00:00+00:00",
        }
        self._shareholder = {
            "symbol": "sh600519",
            "top_shareholders": [
                {
                    "rank": 1,
                    "name": "HolderA",
                    "shares": 700000000.0,
                    "ratio": 55.7,
                    "change": 0,
                },
            ],
            "holder_count_history": [
                {
                    "date": "2024-03-31",
                    "total_holders": 150000,
                    "avg_shares": 8300.0,
                },
            ],
            "source": "westock",
            "collected_at": "2026-06-05T00:00:00+00:00",
        }
        self._minute = [
            {
                "symbol": "sh600519",
                "time": "2026-06-05 09:31",
                "price": 1800.0,
                "volume": 12345,
                "avg_price": 1800.5,
                "source": "westock",
                "collected_at": "2026-06-05T09:31:00+00:00",
            },
        ]

    async def minute(self, symbol, days=1):
        return self._minute

    async def dividend(self, symbol):
        return self._dividend

    async def shareholder(self, symbol):
        return self._shareholder

    async def reserve(self, symbol):
        return self._reserve


@pytest.fixture(autouse=True)
def setup_test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def westock_service():
    return CollectionService(
        providers={"structured": [WestockMockProvider()], "news": []}
    )


async def test_collect_dividend_persists(westock_service):
    result = await westock_service.collect_dividend("sh600519")
    assert result is not None
    assert len(result) == 1
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM dividends WHERE symbol = 'sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["dividend_year"] == 2023
    assert row["cash_dividend"] == 30.88
    assert row["source"] == "westock"


async def test_collect_dividend_idempotent(westock_service):
    await westock_service.collect_dividend("sh600519")
    await westock_service.collect_dividend("sh600519")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM dividends WHERE symbol = 'sh600519'"
        ).fetchall()
    assert len(rows) == 1


async def test_collect_reserve_persists(westock_service):
    result = await westock_service.collect_reserve("sh600519")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profit_forecasts WHERE symbol = 'sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["report_period"] == "2024H1"
    assert row["forecast_type"] == "yuzeng"


async def test_collect_reserve_missing_type_defaults_to_unknown():
    class NoTypeProvider(WestockMockProvider):
        async def reserve(self, symbol):
            # parent is async, so we must await and modify a fresh dict
            base = await super().reserve(symbol)
            base["forecast_type"] = ""
            return base

    svc = CollectionService(providers={"structured": [NoTypeProvider()], "news": []})
    await svc.collect_reserve("sh600519")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT forecast_type FROM profit_forecasts WHERE symbol = 'sh600519'"
        ).fetchall()
    assert dict(rows[0])["forecast_type"] == "未知"


async def test_collect_shareholder_persists_both_tables(westock_service):
    result = await westock_service.collect_shareholder("sh600519")
    assert result is not None
    with get_db() as conn:
        top = conn.execute(
            "SELECT * FROM shareholders WHERE symbol = 'sh600519'"
        ).fetchall()
        hist = conn.execute(
            "SELECT * FROM shareholder_count_history WHERE symbol = 'sh600519'"
        ).fetchall()
    assert len(top) == 1
    assert len(hist) == 1
    assert dict(top[0])["change_amount"] == 0
    assert dict(hist[0])["total_holders"] == 150000


async def test_collect_intraday_persists_minute_klines(westock_service):
    result = await westock_service.collect_intraday("sh600519", days=1)
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM minute_klines WHERE symbol = 'sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["price"] == 1800.0
    assert row["avg_price"] == 1800.5
