from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.asset_service import AssetService

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

_service = AssetService()


class AssetCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    name: Optional[str] = None
    market: Optional[str] = None
    asset_type: str = Field(default="stock")
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class AssetUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class AssetSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    market: Optional[str] = None


@router.post("", status_code=201)
def create_asset(body: AssetCreateRequest) -> dict:
    try:
        data = body.model_dump(exclude_none=True)
        return _service.add_asset(data)
    except ValueError as e:
        msg = str(e)
        if "已在追踪列表" in msg:
            raise HTTPException(
                status_code=409,
                detail={"error": "ASSET_EXISTS", "detail": msg},
            )
        if "无法识别" in msg:
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_SYMBOL", "detail": msg},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "detail": msg},
        )


@router.get("")
def list_assets(
    enabled: Optional[bool] = Query(default=None),
    market: Optional[str] = Query(default=None),
    asset_type: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    filters: dict = {}
    if enabled is not None:
        filters["enabled"] = enabled
    if market is not None:
        filters["market"] = market
    if asset_type is not None:
        filters["asset_type"] = asset_type
    if tag is not None:
        filters["tag"] = tag
    return _service.get_assets(filters=filters or None, page=page, page_size=page_size)


@router.get("/{asset_id}")
def get_asset(asset_id: int) -> dict:
    result = _service.get_asset_by_id(asset_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ASSET_NOT_FOUND", "detail": f"标的 ID {asset_id} 不存在"},
        )
    return result


@router.patch("/{asset_id}")
def update_asset(asset_id: int, body: AssetUpdateRequest) -> dict:
    data = body.model_dump(exclude_none=True)
    result = _service.update_asset(asset_id, data)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ASSET_NOT_FOUND", "detail": f"标的 ID {asset_id} 不存在"},
        )
    return result


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, soft: bool = Query(default=True)) -> None:
    success = _service.delete_asset(asset_id, soft=soft)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": "ASSET_NOT_FOUND", "detail": f"标的 ID {asset_id} 不存在"},
        )


@router.post("/search")
def search_assets(body: AssetSearchRequest) -> dict:
    items = _service.search_assets(keyword=body.keyword, market=body.market)
    return {"items": items, "total": len(items)}
