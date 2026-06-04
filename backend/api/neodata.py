from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.collectors.neodata_client import NeoDataClient
from backend.config import get_config

router = APIRouter(prefix="/api/v1/neodata", tags=["neodata"])


def _get_client() -> NeoDataClient:
    config = get_config()
    data_sources = config.get("data_sources", {})
    news_sources = data_sources.get("news", [])
    neodata_cfg = next((s for s in news_sources if s.get("provider") == "NeoDataProvider"), {})
    params = neodata_cfg.get("params") or {}
    return NeoDataClient(
        endpoint=params.get("endpoint", "https://copilot.tencent.com/agenttool/v1/neodata"),
        config_token=params.get("token") or None,
        timeout=neodata_cfg.get("timeout", 30),
    )


_client_cache: NeoDataClient | None = None


def _get_or_create_client() -> NeoDataClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = _get_client()
    return _client_cache


class TokenSaveRequest(BaseModel):
    token: str = Field(..., min_length=1)


@router.get("/token-status")
async def get_token_status() -> dict:
    return _get_or_create_client().get_token_status()


@router.post("/token")
async def save_token(body: TokenSaveRequest, x_api_key: str | None = Header(None, alias="X-API-Key")) -> dict:
    config = get_config()
    expected_key = config.get("security", {}).get("api_key", "marketlens-local")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail={"error": "UNAUTHORIZED", "detail": "无效或缺失的 API Key"})
    _get_or_create_client().save_token(body.token)
    return {"message": "Token saved successfully"}
