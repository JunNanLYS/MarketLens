import os
import re

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from backend.api.dependencies import verify_api_key
from backend.collectors.neodata_client import NeoDataClient
from backend.config import get_config

router = APIRouter(prefix="/api/v1/neodata", tags=["neodata"])


def _get_client() -> NeoDataClient:
    config = get_config()
    data_sources = config.get("data_sources", {})
    news_sources = data_sources.get("news", [])
    neodata_cfg = next(
        (s for s in news_sources if s.get("provider") == "NeoDataProvider"), {}
    )
    params = neodata_cfg.get("params") or {}
    return NeoDataClient(
        endpoint=params.get(
            "endpoint", "https://copilot.tencent.com/agenttool/v1/neodata"
        ),
        config_token=params.get("token") or None,
        timeout=neodata_cfg.get("timeout", 30),
    )


_client_cache: NeoDataClient | None = None


def _get_or_create_client() -> NeoDataClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = _get_client()
    return _client_cache


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TokenSaveRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=8192)

    @field_validator("token")
    @classmethod
    def _strip_control_chars(cls, v: str) -> str:
        if _CONTROL_CHARS.search(v):
            raise ValueError("token 含非法控制字符")
        return v


@router.get("/token-status")
async def get_token_status() -> dict:
    """返回 NeoData token 状态（不暴露过期时间）。"""
    raw = _get_or_create_client().get_token_status()
    return {
        "is_valid": bool(raw.get("has_token", False)),
        "source": raw.get("source"),
    }


@router.post("/token")
async def save_token(
    body: TokenSaveRequest,
    _auth: None = Depends(verify_api_key),
) -> dict:
    config = get_config()
    expected_key = config.get("security", {}).get("api_key", "marketlens-local")
    if expected_key == "marketlens-local" and not os.getenv("MARKETLENS_API_KEY"):
        logger.warning(
            'NeoData token 端点仍使用默认 API Key "marketlens-local"。'
            "生产环境请通过环境变量 MARKETLENS_API_KEY 或 config.yaml 覆盖。"
        )
    _get_or_create_client().save_token(body.token)
    return {"message": "Token saved successfully"}
