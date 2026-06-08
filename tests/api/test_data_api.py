"""Tests for /api/v1/data/dividend, /shareholder, /reserve, /minute endpoints.

覆盖范围：
- 4 个 GET 查询端点：成功 / 404
- 4 个 POST /refresh 触发端点：成功 / 502（采集失败）
- DB 辅助函数在 CollectionService 层的边界（get_dividends / get_shareholders
  / get_profit_forecasts / get_minute_klines）

策略：
- 通过 init_db_sync() 创建隔离 SQLite，预填测试数据。
- 通过 patch('backend.api.data._service', mock_service) 注入受控 service，
  避免触发真实 WeStockProvider 网络调用。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.collection_service import CollectionService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db() -> None:
    """每个测试独立 SQLite 文件，避免状态污染。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


def _insert_dividends(symbol: str, rows: list[dict]) -> None:
    with get_db() as conn:
        for r in rows:
            conn.execute(
                """INSERT OR IGNORE INTO dividends
                   (symbol, ex_date, cash_dividend, share_bonus,
                    record_date, announce_date, dividend_year, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    r.get("ex_date"),
                    r.get("cash_dividend"),
                    r.get("share_bonus"),
                    r.get("record_date"),
                    r.get("announce_date"),
                    r.get("dividend_year"),
                    r.get("source"),
                    r.get("collected_at"),
                ),
            )


def _insert_shareholders(
    symbol: str, top: list[dict], count_hist: list[dict] | None = None
) -> None:
    with get_db() as conn:
        for r in top:
            conn.execute(
                """INSERT OR IGNORE INTO shareholders
                   (symbol, report_period, rank, name, shares, ratio, change_amount,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    r.get("report_period"),
                    r.get("rank"),
                    r.get("name"),
                    r.get("shares"),
                    r.get("ratio"),
                    r.get("change_amount"),
                    r.get("source"),
                    r.get("collected_at"),
                ),
            )
        for r in count_hist or []:
            conn.execute(
                """INSERT OR IGNORE INTO shareholder_count_history
                   (symbol, report_date, total_holders, avg_shares, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    r.get("report_date"),
                    r.get("total_holders"),
                    r.get("avg_shares"),
                    r.get("source"),
                    r.get("collected_at"),
                ),
            )


def _insert_forecasts(symbol: str, rows: list[dict]) -> None:
    with get_db() as conn:
        for r in rows:
            conn.execute(
                """INSERT OR IGNORE INTO profit_forecasts
                   (symbol, report_period, forecast_type, profit_lower, profit_upper,
                    change_lower, change_upper, summary, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    r.get("report_period"),
                    r.get("forecast_type"),
                    r.get("profit_lower"),
                    r.get("profit_upper"),
                    r.get("change_lower"),
                    r.get("change_upper"),
                    r.get("summary"),
                    r.get("source"),
                    r.get("collected_at"),
                ),
            )


def _insert_minute(symbol: str, rows: list[dict]) -> None:
    with get_db() as conn:
        for r in rows:
            conn.execute(
                """INSERT OR IGNORE INTO minute_klines
                   (symbol, time, price, volume, avg_price, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    r.get("time"),
                    r.get("price"),
                    r.get("volume"),
                    r.get("avg_price"),
                    r.get("source"),
                    r.get("collected_at"),
                ),
            )


def _mock_service(**overrides: Any) -> MagicMock:
    """构造 mock CollectionService 实例，未指定的方法返回合理默认值。"""
    svc = MagicMock(spec=CollectionService)
    # 同步 GET 端点依赖
    svc.get_dividends.return_value = overrides.pop("get_dividends", [])
    svc.get_shareholders.return_value = overrides.pop(
        "get_shareholders",
        {"top_shareholders": [], "holder_count_history": []},
    )
    svc.get_profit_forecasts.return_value = overrides.pop("get_profit_forecasts", [])
    svc.get_minute_klines.return_value = overrides.pop("get_minute_klines", [])
    # 异步 POST 端点依赖（使用 AsyncMock 才能 await）
    svc.collect_dividend = AsyncMock(
        return_value=overrides.pop("collect_dividend", None)
    )
    svc.collect_shareholder = AsyncMock(
        return_value=overrides.pop("collect_shareholder", None)
    )
    svc.collect_reserve = AsyncMock(return_value=overrides.pop("collect_reserve", None))
    svc.collect_intraday = AsyncMock(
        return_value=overrides.pop("collect_intraday", None)
    )
    return svc


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """默认 client：所有查询端点返回空，触发端点返回 None（502）。"""
    monkeypatch.setattr("backend.api.data._service", _mock_service())
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET 端点：分红
# ---------------------------------------------------------------------------


async def test_get_dividend_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """GET /dividend/{symbol} 命中已落库数据。"""
    _insert_dividends(
        "sh600519",
        [
            {
                "ex_date": "2024-06-15",
                "cash_dividend": 30.88,
                "share_bonus": 0,
                "record_date": "2024-06-14",
                "announce_date": "2024-05-30",
                "dividend_year": 2023,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
            {
                "ex_date": "2023-06-20",
                "cash_dividend": 25.91,
                "share_bonus": 0,
                "record_date": "2023-06-19",
                "announce_date": "2023-05-25",
                "dividend_year": 2022,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
        ],
    )
    # DB 已填充，真实 service 可直接查询
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    resp = client.get("/api/v1/data/dividend/sh600519")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "sh600519"
    assert body["total"] == 2
    assert body["items"][0]["ex_date"] == "2024-06-15"
    assert body["items"][0]["cash_dividend"] == 30.88


async def test_get_dividend_no_data(client: TestClient) -> None:
    """GET /dividend/{symbol} 无数据时返回 404。"""
    resp = client.get("/api/v1/data/dividend/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "NO_DATA"
    assert "nonexistent" in body["detail"]


async def test_get_dividend_source_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """source 查询参数应被透传到 DB。"""
    _insert_dividends(
        "sh600519",
        [
            {
                "ex_date": "2024-06-15",
                "cash_dividend": 30.88,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
            {
                "ex_date": "2024-06-16",
                "cash_dividend": 99.0,
                "source": "neodata",
                "collected_at": "2026-05-31T16:00:00",
            },
        ],
    )
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    resp = client.get("/api/v1/data/dividend/sh600519?source=neodata")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "neodata"


# ---------------------------------------------------------------------------
# GET 端点：股东
# ---------------------------------------------------------------------------


async def test_get_shareholder_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """GET /shareholder/{symbol} 返回 top + count_history。"""
    _insert_shareholders(
        "sh600519",
        top=[
            {
                "report_period": "2024-03-31",
                "rank": 1,
                "name": "贵州茅台酒厂集团",
                "shares": 700_000_000,
                "ratio": 55.7,
                "change_amount": 0,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
            {
                "report_period": "2024-03-31",
                "rank": 2,
                "name": "香港中央结算",
                "shares": 95_000_000,
                "ratio": 7.5,
                "change_amount": -1_000_000,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
        ],
        count_hist=[
            {
                "report_date": "2024-03-31",
                "total_holders": 250_000,
                "avg_shares": 5_000,
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
        ],
    )
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    resp = client.get("/api/v1/data/shareholder/sh600519")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "sh600519"
    assert len(body["top_shareholders"]) == 2
    assert len(body["holder_count_history"]) == 1
    assert body["top_shareholders"][0]["rank"] == 1
    assert body["holder_count_history"][0]["total_holders"] == 250_000


async def test_get_shareholder_no_data(client: TestClient) -> None:
    """GET /shareholder/{symbol} 无数据时返回 404。"""
    resp = client.get("/api/v1/data/shareholder/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"] == "NO_DATA"


# ---------------------------------------------------------------------------
# GET 端点：业绩预告
# ---------------------------------------------------------------------------


async def test_get_reserve_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """GET /reserve/{symbol} 命中已落库业绩预告。"""
    _insert_forecasts(
        "sh600519",
        [
            {
                "report_period": "2024Q3",
                "forecast_type": "略增",
                "profit_lower": 60_000_000_000,
                "profit_upper": 65_000_000_000,
                "change_lower": 5.0,
                "change_upper": 10.0,
                "summary": "业绩略增",
                "source": "westock",
                "collected_at": "2026-05-31T16:00:00",
            },
        ],
    )
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    resp = client.get("/api/v1/data/reserve/sh600519")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["forecast_type"] == "略增"
    assert body["items"][0]["profit_lower"] == 60_000_000_000


async def test_get_reserve_no_data(client: TestClient) -> None:
    """GET /reserve/{symbol} 无数据时返回 404。"""
    resp = client.get("/api/v1/data/reserve/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"] == "NO_DATA"


# ---------------------------------------------------------------------------
# GET 端点：分时 K
# ---------------------------------------------------------------------------


async def test_get_minute_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """GET /minute/{symbol} 命中已落库分时数据。"""
    _insert_minute(
        "sh600519",
        [
            {
                "time": "2026-05-31T09:31:00+08:00",
                "price": 1790.0,
                "volume": 10_000,
                "avg_price": 1790.0,
                "source": "westock",
                "collected_at": "2026-05-31T09:31:00+08:00",
            },
            {
                "time": "2026-05-31T09:32:00+08:00",
                "price": 1792.5,
                "volume": 12_000,
                "avg_price": 1791.2,
                "source": "westock",
                "collected_at": "2026-05-31T09:32:00+08:00",
            },
        ],
    )
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    resp = client.get("/api/v1/data/minute/sh600519")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2


async def test_get_minute_with_time_range(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_db: None
) -> None:
    """GET /minute/{symbol}?from=...&to=... 应用时间过滤。"""
    _insert_minute(
        "sh600519",
        [
            {
                "time": "2026-05-31T09:31:00+08:00",
                "price": 1790.0,
                "source": "westock",
                "collected_at": "2026-05-31T09:31:00+08:00",
            },
            {
                "time": "2026-05-31T09:32:00+08:00",
                "price": 1792.5,
                "source": "westock",
                "collected_at": "2026-05-31T09:32:00+08:00",
            },
            {
                "time": "2026-05-31T09:33:00+08:00",
                "price": 1795.0,
                "source": "westock",
                "collected_at": "2026-05-31T09:33:00+08:00",
            },
        ],
    )
    monkeypatch.setattr("backend.api.data._service", CollectionService())
    # 只取 9:32 一条
    resp = client.get(
        "/api/v1/data/minute/sh600519?from=2026-05-31T09:32:00%2B08:00&to=2026-05-31T09:32:30%2B08:00"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["price"] == 1792.5


async def test_get_minute_no_data(client: TestClient) -> None:
    """GET /minute/{symbol} 无数据时返回 404。"""
    resp = client.get("/api/v1/data/minute/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"] == "NO_DATA"


# ---------------------------------------------------------------------------
# POST /refresh 端点：触发采集
# ---------------------------------------------------------------------------


async def test_refresh_dividend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /dividend/{symbol}/refresh 成功时返回采集结果。"""
    svc = _mock_service(
        collect_dividend=[
            {"ex_date": "2024-06-15", "cash_dividend": 30.88, "source": "westock"},
        ]
    )
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/dividend/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "sh600519"
    assert body["total"] == 1
    svc.collect_dividend.assert_awaited_once_with("sh600519")


async def test_refresh_dividend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /dividend/{symbol}/refresh 采集失败时返回 502。"""
    svc = _mock_service(collect_dividend=None)
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/dividend/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "COLLECT_FAILED"


async def test_refresh_shareholder_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /shareholder/{symbol}/refresh 成功时返回 top + count_history。"""
    svc = _mock_service(
        collect_shareholder={
            "top_shareholders": [{"rank": 1, "name": "测试股东"}],
            "holder_count_history": [
                {"report_date": "2024-03-31", "total_holders": 100}
            ],
        }
    )
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/shareholder/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "top_shareholders" in body
    assert "holder_count_history" in body
    svc.collect_shareholder.assert_awaited_once_with("sh600519")


async def test_refresh_shareholder_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /shareholder/{symbol}/refresh 采集失败时返回 502。"""
    svc = _mock_service(collect_shareholder=None)
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/shareholder/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "COLLECT_FAILED"


async def test_refresh_reserve_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /reserve/{symbol}/refresh 成功时返回业绩预告。"""
    svc = _mock_service(
        collect_reserve={
            "report_period": "2024Q3",
            "forecast_type": "略增",
            "profit_lower": 60_000_000_000,
        }
    )
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/reserve/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecast_type"] == "略增"
    svc.collect_reserve.assert_awaited_once_with("sh600519")


async def test_refresh_reserve_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /reserve/{symbol}/refresh 采集失败时返回 502。"""
    svc = _mock_service(collect_reserve=None)
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/reserve/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "COLLECT_FAILED"


async def test_refresh_minute_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /minute/{symbol}/refresh 成功时返回分时数据。"""
    svc = _mock_service(
        collect_intraday=[
            {"time": "2026-05-31T09:31:00+08:00", "price": 1790.0},
        ]
    )
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/minute/sh600519/refresh?days=1",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "sh600519"
    assert body["total"] == 1
    svc.collect_intraday.assert_awaited_once_with("sh600519", days=1)


async def test_refresh_minute_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /minute/{symbol}/refresh 采集失败时返回 502。"""
    svc = _mock_service(collect_intraday=None)
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/minute/sh600519/refresh",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "COLLECT_FAILED"


async def test_refresh_minute_days_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /minute/{symbol}/refresh?days=99 应被 Query 拒绝（le=5）。"""
    svc = _mock_service()
    monkeypatch.setattr("backend.api.data._service", svc)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/data/minute/sh600519/refresh?days=99",
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 422
    svc.collect_intraday.assert_not_awaited()
