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
    assert data["has_token"] is True
    assert data["source"] == "config"
    assert data["expires_at"] is None
    mock_client.get_token_status.assert_called_once()


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


async def test_save_token_empty_returns_400(
    test_client: TestClient, mock_client: MagicMock
) -> None:
    resp = test_client.post(
        "/api/v1/neodata/token",
        json={"token": ""},
        headers={"X-API-Key": "marketlens-local"},
    )
    assert resp.status_code == 422
    mock_client.save_token.assert_not_called()
