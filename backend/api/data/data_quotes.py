"""Router for quotes (行情 + K线 + 分时) endpoints of /api/v1/data."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.data._service import _get_service
from backend.api.neodata import verify_api_key


router = APIRouter()
@router.get("/quotes/{symbol}")
def get_quote(symbol: str) -> dict:
    quote = _get_service().get_quote(symbol)
    if quote is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "SYMBOL_NOT_FOUND",
                "detail": f"标的 '{symbol}' 无行情数据",
            },
        )
    return quote


@router.post("/quotes/{symbol}/refresh")
async def refresh_quote(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    result = await _get_service().collect_quote_single(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "REFRESH_FAILED",
                "detail": f"标的 '{symbol}' 数据刷新失败",
            },
        )
    return result


@router.get("/quotes/{symbol}/history")
def get_quote_history(
    symbol: str,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    from_dt = from_.isoformat() if from_ else None
    to_dt = to.isoformat() if to else None
    items = _get_service().get_quote_history(
        symbol, limit=limit, from_dt=from_dt, to_dt=to_dt
    )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/kline/{symbol}")
def get_kline(
    symbol: str,
    limit: int = Query(60, ge=1, le=365),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None, alias="to"),
) -> dict:
    from_date = from_.isoformat() if from_ else None
    to_date = to.isoformat() if to else None
    items = _get_service().get_kline(
        symbol, limit=limit, from_date=from_date, to_date=to_date
    )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/intraday/{symbol}")
async def get_intraday(
    symbol: str,
    days: int = Query(1, ge=1, le=5),
    _auth: None = Depends(verify_api_key),
) -> dict:
    result = await _get_service().collect_intraday(symbol, days=days)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 '{symbol}' 分时数据采集失败",
            },
        )
    return {"symbol": symbol, "items": result}


@router.get("/minute/{symbol}")
def get_minute_klines(
    symbol: str,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None, alias="to"),
    limit: int = Query(240, ge=1, le=1440),
) -> dict:
    """查询分时 K 线（按 time 降序）。"""
    from_dt = from_.isoformat() if from_ else None
    to_dt = to.isoformat() if to else None
    items = _get_service().get_minute_klines(
        symbol, limit=limit, from_dt=from_dt, to_dt=to_dt
    )
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"标的 {symbol} 无分时数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


# ============================================================================
# 4 个 /refresh 端点（POST 主动触发采集）
# 保留 /dividend、/shareholder、/reserve、/intraday 老路径以兼容现有调用方
# ============================================================================


@router.post("/minute/{symbol}/refresh")
async def refresh_minute(
    symbol: str,
    days: int = Query(1, ge=1, le=5),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发分时数据采集并落库。"""
    items = await _get_service().collect_intraday(symbol, days=days)
    if items is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 {symbol} 分时数据采集失败",
            },
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


# ============================================================================
# 阶段 14：ETF 全套（5 个 GET 查询 + 1 个 POST refresh）
# 走 POST /etf-refresh/{symbol} 触发采集（一次性拉 5 类数据）
# ============================================================================


