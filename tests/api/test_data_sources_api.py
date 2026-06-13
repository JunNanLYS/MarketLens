"""Tests for GET /api/v1/data-sources/status.

Mock strategy:
- `NeoDataClient` is constructed inside the endpoint handler (per request).
  We patch the class so the construction returns a MagicMock with
  get_token_status() controlled by each test.
- `shutil.which` is patched for westock's command_resolved path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


def _neo_client_factory(
    has_token: bool, source: str = "cache", expires_at: str | None = None
):
    """Factory used as `side_effect` for the NeoDataClient patch.

    Using a factory (not `return_value=mock_instance`) keeps the mock object
    distinct from a real NeoDataClient, so MagicMock's auto-spec behavior
    doesn't shadow the configured get_token_status return value.
    """

    def factory(*args, **kwargs):
        m = MagicMock()
        m.get_token_status.return_value = {
            "has_token": has_token,
            "source": source,
            "expires_at": expires_at,
            "verified": False,
        }
        return m

    return factory


def test_status_returns_three_top_level_keys() -> None:
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(True),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/data-sources/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"structured", "news", "hint"}
    assert isinstance(body["structured"], list)
    assert isinstance(body["news"], list)


def test_neodata_with_token_reports_has_token_true() -> None:
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(
            True, source="cache", expires_at="2027-01-01T00:00:00"
        ),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/data-sources/status")
    body = resp.json()
    neo = next(s for s in body["structured"] if s["provider"] == "NeoDataProvider")
    assert neo["has_token"] is True
    assert neo["token_source"] == "cache"
    assert neo["token_expires_at"] == "2027-01-01T00:00:00"
    assert neo["token_verified"] is False
    assert neo["optional"] is True


def test_neodata_without_token_reports_has_token_false_with_error_hint() -> None:
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(False, source="none", expires_at=None),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/data-sources/status")
    body = resp.json()
    neo = next(s for s in body["structured"] if s["provider"] == "NeoDataProvider")
    assert neo["has_token"] is False
    assert neo["token_source"] == "none"


def test_westock_command_resolved_true_when_executable_exists() -> None:
    # westock 的 command 字段是 `westock-data-clawhub`(2026-06-13 改:不再
    # 走 npx)。mock shutil.which 返回该 wrapper 的绝对路径,验证:
    # - executable = 返回路径的 basename = "westock-data-clawhub"
    # - command = 配置文件原始值
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(True),
    ):
        with patch(
            "backend.api.data_sources.shutil.which",
            return_value="C:/Users/xxx/AppData/Roaming/npm/westock-data-clawhub",
        ):
            client = TestClient(app)
            resp = client.get("/api/v1/data-sources/status")
    body = resp.json()
    westock = next(s for s in body["structured"] if s["provider"] == "WeStockProvider")
    assert westock["executable"] == "westock-data-clawhub"
    assert westock["command_resolved"] is True
    assert westock["command"] == "westock-data-clawhub"


def test_westock_command_resolved_false_when_executable_missing() -> None:
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(True),
    ):
        with patch("backend.api.data_sources.shutil.which", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/v1/data-sources/status")
    body = resp.json()
    westock = next(s for s in body["structured"] if s["provider"] == "WeStockProvider")
    assert westock["command_resolved"] is False


def test_generic_http_source_exposes_endpoint() -> None:
    with patch(
        "backend.api.data_sources.NeoDataClient",
        side_effect=_neo_client_factory(True),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/data-sources/status")
    body = resp.json()
    rss = next(s for s in body["news"] if s["provider"] == "RSSProvider")
    assert rss["endpoint"] == "https://feeds.bbci.co.uk/news/world/rss.xml"
    assert rss["optional"] is True
    assert rss["configured"] is True


def test_status_does_not_raise_when_token_status_throws() -> None:
    """Endpoint must never crash even if NeoDataClient.get_token_status fails."""

    def factory(*args, **kwargs):
        m = MagicMock()
        m.get_token_status.side_effect = RuntimeError("disk read error")
        return m

    with patch("backend.api.data_sources.NeoDataClient", side_effect=factory):
        client = TestClient(app)
        resp = client.get("/api/v1/data-sources/status")
    assert resp.status_code == 200
    body = resp.json()
    neo = next(s for s in body["structured"] if s["provider"] == "NeoDataProvider")
    # Falls back to a known-empty status
    assert neo["has_token"] is False
    assert neo["token_source"] == "none"
