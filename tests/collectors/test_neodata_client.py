import base64
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from backend.collectors.neodata_client import NeoDataClient, TokenManager


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".workbuddy"
    d.mkdir()
    return d


@pytest.fixture
def cache_file(cache_dir: Path) -> Path:
    return cache_dir / ".neodata_token"


@pytest.fixture
def token_manager(cache_file: Path) -> TokenManager:
    with patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file):
        yield TokenManager()


def _write_cache(cache_file: Path, token: str, saved_at: int) -> None:
    data = {"token": token, "saved_at": saved_at}
    cache_file.write_text(json.dumps(data), encoding="utf-8")


async def test_token_manager_reads_from_cache(
    token_manager: TokenManager, cache_file: Path
) -> None:
    _write_cache(cache_file, "cached_tok_123", int(time.time()))
    token, source = token_manager.get_token()
    assert token == "cached_tok_123"
    assert source == "cache"


async def test_token_manager_detects_expired_token(
    token_manager: TokenManager, cache_file: Path
) -> None:
    _write_cache(cache_file, "expired_tok", int(time.time()) - 43201)
    token, source = token_manager.get_token()
    assert token is None
    assert source == "none"


async def test_token_manager_fallback_to_config_token(
    token_manager: TokenManager, cache_file: Path
) -> None:
    cache_file.unlink(missing_ok=True)
    mgr = TokenManager(config_token="config_tok_abc")
    with patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file):
        token, source = mgr.get_token()
    assert token == "config_tok_abc"
    assert source == "config"


async def test_token_manager_fallback_to_env_var(
    token_manager: TokenManager, cache_file: Path
) -> None:
    cache_file.unlink(missing_ok=True)
    with patch.dict("os.environ", {"NEODATA_TOKEN": "env_tok_xyz"}):
        with patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file):
            token, source = token_manager.get_token()
    assert token == "env_tok_xyz"
    assert source == "env"


async def test_token_manager_save_token(
    token_manager: TokenManager, cache_file: Path
) -> None:
    token_manager.save_token("new_tok_save")
    raw = cache_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["token"] == "new_tok_save"
    assert "saved_at" in data


async def test_token_manager_get_status(
    token_manager: TokenManager, cache_file: Path
) -> None:
    _write_cache(cache_file, "status_tok", int(time.time()))
    status = token_manager.get_status()
    assert status["has_token"] is True
    assert status["source"] == "cache"
    assert status["expires_at"] is not None


async def test_neodata_client_query_returns_none_when_no_token(
    cache_file: Path,
) -> None:
    with patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file):
        client = NeoDataClient(endpoint="https://example.com/api")
        result = await client.query("test query")
    assert result is None


async def test_neodata_client_query_makes_correct_post(
    cache_file: Path,
) -> None:
    _write_cache(cache_file, "valid_tok", int(time.time()))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": "200", "data": {"apiData": {}}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file):
        client = NeoDataClient(endpoint="https://example.com/api")
        client._client = mock_client  # 绕过懒加载直接注入 mock
        result = await client.query("贵州茅台股价", data_type="api")

    assert result == {"code": "200", "data": {"apiData": {}}}
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["query"] == "贵州茅台股价"
    assert payload["channel"] == "neodata"
    assert payload["sub_channel"] == "workbuddy"
    assert payload["data_type"] == "api"
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
    assert headers["Authorization"] == "Bearer valid_tok"


async def test_neodata_client_query_retries_on_auth_error(
    cache_file: Path,
) -> None:
    _write_cache(cache_file, "bad_tok", int(time.time()))

    auth_resp = MagicMock()
    auth_resp.status_code = 401
    auth_resp.json.return_value = {"code": "40101", "msg": "token expired"}
    auth_resp.raise_for_status = MagicMock()

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"code": "200", "data": {}}
    success_resp.raise_for_status = MagicMock()

    call_count = 0

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return auth_resp
        return success_resp

    mock_client = AsyncMock()
    mock_client.post.side_effect = mock_post

    with (
        patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file),
        patch.dict("os.environ", {"NEODATA_TOKEN": "env_fallback_tok"}),
    ):
        client = NeoDataClient(endpoint="https://example.com/api")
        client._client = mock_client
        result = await client.query("test query")

    assert result == {"code": "200", "data": {}}
    assert call_count == 2


async def test_neodata_client_query_returns_none_on_retry_failure(
    cache_file: Path,
) -> None:
    _write_cache(cache_file, "bad_tok", int(time.time()))

    auth_resp = MagicMock()
    auth_resp.status_code = 401
    auth_resp.json.return_value = {"code": "40101", "msg": "token expired"}
    auth_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = auth_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("backend.collectors.neodata_client._TOKEN_FILE", cache_file),
        patch("backend.collectors.neodata_client.httpx.Client", return_value=mock_client),
        patch.dict("os.environ", {"NEODATA_TOKEN": "env_fallback_tok"}),
    ):
        client = NeoDataClient(endpoint="https://example.com/api")
        result = await client.query("test query")

    assert result is None


def _make_jwt_token(exp_offset: int = 3600) -> str:
    """构造一个带指定 exp 偏移的 JWT token 用于测试。"""
    payload = json.dumps({"exp": int(time.time()) + exp_offset, "iss": "codebuddy.cn"})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    return f"header.{payload_b64}.sig"


async def test_token_manager_valid_jwt_not_expired(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """JWT token 在 exp 未到期时应有效，忽略 12h TTL。"""
    jwt = _make_jwt_token(exp_offset=86400 * 300)  # ~300 天后过期
    _write_cache(cache_file, jwt, int(time.time()) - 43201)  # saved_at 已超过 12h
    token, source = token_manager.get_token()
    assert token == jwt, "JWT 应通过 exp 检查，不受 12h TTL 限制"
    assert source == "cache"


async def test_token_manager_expired_jwt_returns_none(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """JWT token exp 已过期时应返回 None。"""
    jwt = _make_jwt_token(exp_offset=-3600)  # 1 小时前已过期
    _write_cache(cache_file, jwt, int(time.time()))
    token, source = token_manager.get_token()
    assert token is None
    assert source == "none"


async def test_token_manager_non_jwt_uses_ttl(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """非 JWT token（不透明字符串）仍使用 12h TTL。"""
    _write_cache(cache_file, "opaque_temp_token", int(time.time()))
    token, _ = token_manager.get_token()
    assert token == "opaque_temp_token"


async def test_token_manager_non_jwt_expired_by_ttl(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """非 JWT token 超过 12h 后应返回 None。"""
    _write_cache(cache_file, "opaque_temp_token", int(time.time()) - 43201)
    token, _ = token_manager.get_token()
    assert token is None


async def test_token_manager_malformed_jwt_falls_back_to_ttl(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """三段式但 payload 非有效 JSON 时回退到 TTL 判断。"""
    jwt = f"header.{'='*4}.sig"  # payload 不是合法 Base64 JSON
    _write_cache(cache_file, jwt, int(time.time()))
    token, _ = token_manager.get_token()
    assert token == jwt


async def test_token_manager_jwt_status_shows_exp(
    token_manager: TokenManager, cache_file: Path
) -> None:
    """get_status 对 JWT token 应返回 exp 对应的过期时间。"""
    jwt = _make_jwt_token(exp_offset=86400 * 100)  # ~100 天后
    _write_cache(cache_file, jwt, int(time.time()))
    status = token_manager.get_status()
    assert status["has_token"] is True
    assert status["source"] == "cache"
    assert status["expires_at"] is not None