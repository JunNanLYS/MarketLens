import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from backend.collectors.base import BaseProvider
from backend.services.collection_service import CollectionService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


class MockProvider(BaseProvider):
    def __init__(
        self,
        name: str = "mock",
        quote_data: list[dict] | None = None,
        kline_data: list[dict] | None = None,
        finance_data: dict | None = None,
        fund_flow_data: dict | None = None,
        technical_data: dict | None = None,
        fail_symbols: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self._quote_data = quote_data or []
        self._kline_data = kline_data or []
        self._finance_data = finance_data or {}
        self._fund_flow_data = fund_flow_data or {}
        self._technical_data = technical_data or {}
        self._fail_symbols = fail_symbols or set()

    async def search(self, keyword: str) -> list[dict]:
        return []

    async def quote(self, symbols: list[str]) -> list[dict]:
        if any(s in self._fail_symbols for s in symbols):
            raise RuntimeError("Provider 采集失败")
        return [q for q in self._quote_data if q.get("symbol") in symbols]

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        if symbol in self._fail_symbols:
            raise RuntimeError("Provider 采集失败")
        return self._kline_data

    async def finance(self, symbol: str) -> dict:
        if symbol in self._fail_symbols:
            raise RuntimeError("Provider 采集失败")
        return self._finance_data

    async def fund_flow(self, symbol: str) -> dict:
        if symbol in self._fail_symbols:
            raise RuntimeError("Provider 采集失败")
        return self._fund_flow_data

    async def technical(self, symbol: str) -> dict:
        if symbol in self._fail_symbols:
            raise RuntimeError("Provider 采集失败")
        return self._technical_data


QUOTE_DATA = [
    {
        "symbol": "sh600519",
        "price": 1800.0,
        "change": 20.0,
        "change_pct": 1.12,
        "open": 1785.0,
        "high": 1810.0,
        "low": 1780.0,
        "prev_close": 1780.0,
        "volume": 5000000,
        "amount": 9000000000.0,
        "amplitude": 1.69,
        "turnover_rate": 0.4,
        "high_52w": 1900.0,
        "low_52w": 1500.0,
        "source": "mock",
        "collected_at": "2026-05-31T15:30:00+00:00",
    },
    {
        "symbol": "hk00700",
        "price": 385.0,
        "change": 4.6,
        "change_pct": 1.2,
        "open": 382.0,
        "high": 387.5,
        "low": 381.0,
        "prev_close": 380.4,
        "volume": 23456789,
        "amount": 9034567890.0,
        "amplitude": 1.71,
        "turnover_rate": 0.25,
        "high_52w": 420.0,
        "low_52w": 310.0,
        "source": "mock",
        "collected_at": "2026-05-31T15:30:00+00:00",
    },
]

KLINE_DATA = [
    {"symbol": "sh600519", "date": "2026-05-30", "open": 1780.0, "high": 1810.0, "low": 1775.0, "close": 1800.0, "volume": 5000000, "change_pct": 1.12, "source": "mock", "collected_at": "2026-05-31T16:05:00+00:00"},
    {"symbol": "sh600519", "date": "2026-05-29", "open": 1770.0, "high": 1790.0, "low": 1765.0, "close": 1780.0, "volume": 4500000, "change_pct": -0.5, "source": "mock", "collected_at": "2026-05-31T16:05:00+00:00"},
]

FINANCE_DATA = {
    "symbol": "sh600519",
    "report_period": "2026Q1",
    "revenue": 50000000000.0,
    "revenue_yoy": 8.5,
    "net_profit": 25000000000.0,
    "net_profit_yoy": 12.3,
    "eps": 19.9,
    "roe": 22.5,
    "debt_ratio": 30.0,
    "gross_margin": 91.0,
    "net_margin": 50.0,
    "source": "mock",
    "collected_at": "2026-05-31T16:05:00+00:00",
}

FUND_FLOW_DATA = {
    "symbol": "sh600519",
    "date": "2026-05-31",
    "main_net_inflow": 380000000,
    "super_large_net_inflow": 150000000,
    "large_net_inflow": 230000000,
    "medium_net_inflow": -50000000,
    "small_net_inflow": -120000000,
    "net_inflow_ratio": 4.2,
    "source": "mock",
    "collected_at": "2026-05-31T16:05:00+00:00",
}

TECHNICAL_DATA = {
    "symbol": "sh600519",
    "date": "2026-05-31",
    "ma5": 1790.0,
    "ma10": 1785.0,
    "ma20": 1780.0,
    "ma60": 1750.0,
    "macd_dif": 5.2,
    "macd_dea": 3.8,
    "macd_histogram": 1.4,
    "rsi6": 62.3,
    "rsi14": 58.7,
    "boll_upper": 1820.0,
    "boll_middle": 1780.0,
    "boll_lower": 1740.0,
    "volume_ma5": 4800000,
    "volume_ma20": 4500000,
    "source": "mock",
    "collected_at": "2026-05-31T16:05:00+00:00",
}


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


def _insert_assets(*symbols: str) -> None:
    with get_db() as conn:
        for symbol in symbols:
            market = symbol[:2] if symbol[:2] in ("sh", "sz", "hk", "us") else "sh"
            conn.execute(
                """INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled)
                   VALUES (?, ?, ?, 'stock', 1)""",
                (symbol, symbol, market),
            )


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider(
        name="mock",
        quote_data=QUOTE_DATA,
        kline_data=KLINE_DATA,
        finance_data=FINANCE_DATA,
        fund_flow_data=FUND_FLOW_DATA,
        technical_data=TECHNICAL_DATA,
    )


@pytest.fixture
def service(mock_provider: MockProvider) -> CollectionService:
    return CollectionService(providers={"structured": [mock_provider], "news": []})


async def test_collect_quotes_success(service: CollectionService) -> None:
    _insert_assets("sh600519", "hk00700")
    result = await service.collect_quotes()
    assert result["success"] == 2
    assert result["failed"] == 0
    assert result["total"] == 2


async def test_collect_quotes_single_failure_does_not_affect_others() -> None:
    _insert_assets("sh600519", "hk00700", "sz000001")
    fail_provider = MockProvider(
        name="mock",
        quote_data=QUOTE_DATA,
        fail_symbols={"sz000001"},
    )
    svc = CollectionService(providers={"structured": [fail_provider], "news": []})
    result = await svc.collect_quotes()
    assert result["success"] == 2
    assert result["failed"] == 1
    assert result["total"] == 3


async def test_collect_daily_close_success(service: CollectionService) -> None:
    _insert_assets("sh600519")
    result = await service.collect_daily_close()
    assert result["kline"]["success"] > 0
    assert result["finance"]["success"] > 0
    assert result["fund_flow"]["success"] > 0
    assert result["technical"]["success"] > 0


async def test_collect_quotes_saves_raw_data(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_quotes()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM raw_data WHERE data_type = 'quote' AND symbol = 'sh600519'"
        ).fetchall()
    assert len(rows) >= 1
    raw = dict(rows[0])
    assert raw["source"] == "mock"
    parsed = json.loads(raw["raw_json"])
    assert parsed["symbol"] == "sh600519"
    assert parsed["price"] == 1800.0


async def test_collect_daily_close_saves_raw_data(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM raw_data WHERE symbol = 'sh600519'"
        ).fetchall()
    types = {dict(r)["data_type"] for r in rows}
    assert "kline" in types
    assert "finance" in types
    assert "fund_flow" in types
    assert "technical" in types


async def test_get_quote(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_quotes()
    quote = service.get_quote("sh600519")
    assert quote is not None
    assert quote["symbol"] == "sh600519"
    assert quote["price"] == 1800.0
    assert quote["source"] == "mock"
    assert quote["collected_at"] is not None


async def test_get_quote_history(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_quotes()
    history = service.get_quote_history("sh600519", limit=10)
    assert len(history) >= 1
    assert history[0]["symbol"] == "sh600519"


async def test_get_quote_history_with_time_range(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_quotes()
    history = service.get_quote_history(
        "sh600519",
        from_dt="2026-05-31T00:00:00+00:00",
        to_dt="2026-05-31T23:59:59+00:00",
    )
    assert len(history) >= 1


async def test_get_kline(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    kline = service.get_kline("sh600519", limit=10)
    assert len(kline) >= 1
    assert kline[0]["symbol"] == "sh600519"
    assert kline[0]["date"] is not None


async def test_get_finance(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    finance = service.get_finance("sh600519", limit=4)
    assert len(finance) >= 1
    assert finance[0]["symbol"] == "sh600519"
    assert finance[0]["report_period"] == "2026Q1"


async def test_get_fund_flow_with_summary(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    result = service.get_fund_flow("sh600519", days=5)
    assert "items" in result
    assert "summary" in result
    assert len(result["items"]) >= 1
    summary = result["summary"]
    assert "net_flow_5d" in summary
    assert "trend" in summary
    assert "avg_net_inflow_ratio" in summary


async def test_get_technical(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    tech = service.get_technical("sh600519")
    assert tech is not None
    assert tech["symbol"] == "sh600519"
    assert tech["ma5"] == 1790.0
    assert tech["rsi6"] == 62.3


async def test_get_quote_no_data(service: CollectionService) -> None:
    result = service.get_quote("nonexistent")
    assert result is None


async def test_get_quote_history_no_data(service: CollectionService) -> None:
    result = service.get_quote_history("nonexistent")
    assert result == []


async def test_get_kline_no_data(service: CollectionService) -> None:
    result = service.get_kline("nonexistent")
    assert result == []


async def test_get_finance_no_data(service: CollectionService) -> None:
    result = service.get_finance("nonexistent")
    assert result == []


async def test_get_fund_flow_no_data(service: CollectionService) -> None:
    result = service.get_fund_flow("nonexistent")
    assert result["items"] == []
    assert result["summary"]["trend"] == "无数据"


async def test_get_technical_no_data(service: CollectionService) -> None:
    result = service.get_technical("nonexistent")
    assert result is None


async def test_collect_quotes_writes_run_log(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_quotes()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'quote'"
        ).fetchall()
    assert len(rows) == 1
    log = dict(rows[0])
    assert log["status"] == "success"
    assert log["affected_assets"] == 1
    assert log["started_at"] is not None
    assert log["finished_at"] is not None


async def test_collect_daily_close_writes_run_log(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'daily_close'"
        ).fetchall()
    assert len(rows) == 1
    log = dict(rows[0])
    assert log["status"] == "success"
    assert log["affected_assets"] == 1


async def test_collect_quotes_run_log_with_failure() -> None:
    _insert_assets("sh600519", "sz000001")
    fail_provider = MockProvider(
        name="mock",
        quote_data=QUOTE_DATA,
        fail_symbols={"sz000001"},
    )
    svc = CollectionService(providers={"structured": [fail_provider], "news": []})
    await svc.collect_quotes()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'quote'"
        ).fetchall()
    log = dict(rows[0])
    assert log["status"] == "failure"
    assert log["error_message"] is not None
    assert "sz000001" in log["error_message"]


async def test_collect_quote_single(service: CollectionService) -> None:
    _insert_assets("sh600519")
    result = await service.collect_quote_single("sh600519")
    assert result is not None
    assert result["symbol"] == "sh600519"
    assert result["price"] == 1800.0


async def test_collect_quote_single_no_provider() -> None:
    empty_provider = MockProvider(name="empty", quote_data=[])
    svc = CollectionService(providers={"structured": [empty_provider], "news": []})
    result = await svc.collect_quote_single("sh600519")
    assert result is None


async def test_kline_idempotent(service: CollectionService) -> None:
    _insert_assets("sh600519")
    await service.collect_daily_close()
    await service.collect_daily_close()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM kline_daily WHERE symbol = 'sh600519' AND date = '2026-05-30'"
        ).fetchall()
    assert len(rows) == 1


async def test_concurrent_collect_quotes_no_corruption() -> None:
    """并发 collect_quotes 不应产生数据库锁定错误, 且最终行数一致。

    验证 _WRITE_LOCK 串行化生效: 3 次并发采集, 每次 3 资产全成功 = 9。
    """
    import asyncio

    _insert_assets("sh600519", "hk00700", "sz000001")
    svc = CollectionService(providers={"structured": [mock_provider] if False else [], "news": []})
    # 重新构建以使用真正的 mock_provider
    from tests.services.test_collection_service import MockProvider as _MP  # noqa: F401

    # mock_provider 是 fixture,不能直接引用 —— 用 QUOTE_DATA 手动构造
    provider = MockProvider(
        name="mock",
        quote_data=QUOTE_DATA + [
            {
                "symbol": "sz000001",
                "price": 12.5,
                "change": 0.1,
                "change_pct": 0.8,
                "source": "mock",
                "collected_at": "2026-05-31T15:30:00+00:00",
            },
        ],
    )
    svc = CollectionService(providers={"structured": [provider], "news": []})

    results = await asyncio.gather(
        svc.collect_quotes(),
        svc.collect_quotes(),
        svc.collect_quotes(),
    )
    total_success = sum(r["success"] for r in results)
    assert total_success == 9  # 3 次 × 3 资产 = 9




