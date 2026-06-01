from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


_client = _get_client()


class TokenSaveRequest(BaseModel):
    token: str = Field(..., min_length=1)


@router.get("/token-status")
def get_token_status() -> dict:
    return _client.get_token_status()


@router.post("/token")
def save_token(body: TokenSaveRequest) -> dict:
    _client.save_token(body.token)
    return {"message": "Token saved successfully"}
