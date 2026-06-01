from fastapi import APIRouter, HTTPException, Query

from backend.services.news_service import NewsService

router = APIRouter(prefix="/api/v1/news", tags=["news"])

_service = NewsService()


@router.get("")
def list_news(
    symbol: str | None = Query(default=None),
    days: int = Query(default=7, ge=1),
    sentiment: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    filters: dict = {}
    if symbol is not None:
        filters["symbol"] = symbol
    if days is not None:
        filters["days"] = days
    if sentiment is not None:
        filters["sentiment"] = sentiment
    if source is not None:
        filters["source"] = source
    return _service.get_news(filters=filters or None, page=page, page_size=page_size)


@router.get("/{news_id}")
def get_news(news_id: int) -> dict:
    result = _service.get_news_by_id(news_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NEWS_NOT_FOUND", "detail": f"新闻 ID {news_id} 不存在"},
        )
    return result
