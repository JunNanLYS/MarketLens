from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.asset_service import AssetExistsError, AssetService

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

_service = AssetService()


class AssetCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    name: str | None = None
    market: str | None = None
    asset_type: str = Field(default="stock")
    tags: list[str] | None = None
    notes: str | None = None


class AssetUpdateRequest(BaseModel):
    enabled: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None


@router.post("", status_code=201)
async def create_asset(body: AssetCreateRequest) -> dict:
    try:
        data = body.model_dump(exclude_none=True)
        return await _service.add_asset(data)
    except AssetExistsError as e:
        existing = e.existing_asset
        # 注：AssetService.add_asset 对 enabled=0（软删除）的现存记录会重新启用并直接返回，
        # 不抛 AssetExistsError；所以到这里 existing 必然是 enabled=1 的活跃记录。
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ASSET_EXISTS",
                "message": (
                    f"标的 '{existing.get('symbol')}' 已在追踪列表中"
                    f"（ID: {existing.get('id')}）"
                ),
                "existing_asset": existing,
            },
        )
    except ValueError as e:
        msg = str(e)
        if "无法识别" in msg:
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_SYMBOL", "message": msg},
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": msg},
        )


@router.get("")
def list_assets(
    enabled: bool | None = Query(default=None),
    market: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=64),
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
    if search is not None and search.strip():
        filters["search"] = search.strip()
    return _service.get_assets(filters=filters or None, page=page, page_size=page_size)


# 注意：/search 必须在 /{asset_id} 之前声明，否则 FastAPI 会先匹配
# /{asset_id: int} 而把 "search" 解析成 ID 导致 422。
@router.get("/search")
async def search_assets(
    keyword: str = Query(..., min_length=1),
    market: str | None = Query(default=None),
    include_local: bool = Query(default=True, description="外部结果不足时是否回退查本地 tracked_assets"),
) -> dict:
    items = await _service.search_assets(keyword=keyword, market=market, include_local=include_local)
    return {"items": items, "total": len(items)}


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
