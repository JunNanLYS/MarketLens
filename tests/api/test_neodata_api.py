from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.collectors.neodata_client import NeoDataClient
from backend.main import app


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=NeoDataClient)
    client.get_token_status.return_value = {
        "has_token": False,
        "source": "none",
        "expires_at": None,
    }
    return client


@pytest.fixture
async def test_client(mock_client: MagicMock) -> TestClient:
    with patch("backend.api.neodata._client_cache", mock_client):
        yield TestClient(app)


async def test_get_token_status(test_client: TestClient, mock_client: MagicMock) -> None:
    mock_client.get_token_status.return_value = {
        "has_token": True,
        "source": "config",
        "expires_at": None,
    }
    resp = test_client.get("/api/v1/neodata/token-status")
    assert resp.status_code == 200
    data = resp.json()
    # 新 schema:暴露 is_valid + source,不再泄露 expires_at
    assert data["is_valid"] is True
    assert data["source"] == "config"
    assert "expires_at" not in data
    assert "verified" not in data
    mock_client.get_token_status.assert_called_once()


async def test_get_token_status_unconfigured(test_client: TestClient) -> None:
    """未配置 token 时,is_valid 应为 False。"""
    resp = test_client.get("/api/v1/neodata/token-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False
    assert data["source"] == "none"
    assert "expires_at" not in data


async def test_save_token_success(test_client: TestClient, mock_client: MagicMock) -> None:
    resp = test_client.post(
        "/api/v1/neodata/token",
        json={"token": "my_secret_token"},
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Token saved successfully"
    mock_client.save_token.assert_called_once_with("my_secret_token")


async def test_save_token_empty_returns_422(
    test_client: TestClient, mock_client: MagicMock
) -> None:
    resp = test_client.post(
        "/api/v1/neodata/token",
        json={"token": ""},
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 422
    mock_client.save_token.assert_not_called()


async def test_save_token_too_long_returns_422(
    test_client: TestClient, mock_client: MagicMock
) -> None:
    """超过 8192 字符的 token 应被拒绝。"""
    resp = test_client.post(
        "/api/v1/neodata/token",
        json={"token": "x" * 8193},
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 422
    mock_client.save_token.assert_not_called()


async def test_save_token_control_char_returns_422(
    test_client: TestClient, mock_client: MagicMock
) -> None:
    """含控制字符的 token 应被拒绝。"""
    resp = test_client.post(
        "/api/v1/neodata/token",
        json={"token": "hello\x00world"},
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 422
    mock_client.save_token.assert_not_called()
