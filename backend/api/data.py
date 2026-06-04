from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query

from backend.services.collection_service import CollectionService

router = APIRouter(prefix="/api/v1/data", tags=["data"])
_service = CollectionService()


def _format_technical(row: dict) -> dict:
    return {
        "symbol": row.get("symbol"),
        "date": row.get("date"),
        "ma": {"ma5": row.get("ma5"), "ma10": row.get("ma10"), "ma20": row.get("ma20"), "ma60": row.get("ma60")},
        "macd": {"dif": row.get("macd_dif"), "dea": row.get("macd_dea"), "histogram": row.get("macd_histogram")},
        "rsi": {"rsi6": row.get("rsi6"), "rsi14": row.get("rsi14")},
        "boll": {"upper": row.get("boll_upper"), "middle": row.get("boll_middle"), "lower": row.get("boll_lower")},
        "volume_ma": {"ma5": row.get("volume_ma5"), "ma20": row.get("volume_ma20")},
        "source": row.get("source"),
        "collected_at": row.get("collected_at"),
    }


@router.get("/quotes/{symbol}")
def get_quote(symbol: str) -> dict:
    quote = _service.get_quote(symbol)
    if quote is None:
        raise HTTPException(status_code=404, detail={"error": "SYMBOL_NOT_FOUND", "detail": f"标的 '{symbol}' 无行情数据"})
    return quote


@router.post("/quotes/{symbol}/refresh")
async def refresh_quote(symbol: str) -> dict:
    result = await _service.collect_quote_single(symbol)
    if result is None:
        raise HTTPException(status_code=502, detail={"error": "REFRESH_FAILED", "detail": f"标的 '{symbol}' 数据刷新失败"})
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
    items = _service.get_quote_history(symbol, limit=limit, from_dt=from_dt, to_dt=to_dt)
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
    items = _service.get_kline(symbol, limit=limit, from_date=from_date, to_date=to_date)
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/finance/{symbol}")
def get_finance(symbol: str, limit: int = Query(4, ge=1, le=20)) -> dict:
    items = _service.get_finance(symbol, limit=limit)
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/fund-flow/{symbol}")
def get_fund_flow(symbol: str, days: int = Query(5, ge=1, le=30)) -> dict:
    result = _service.get_fund_flow(symbol, days=days)
    return {"symbol": symbol, "items": result["items"], "summary": result["summary"]}


@router.get("/technical/{symbol}")
def get_technical(symbol: str) -> dict:
    row = _service.get_technical(symbol)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "SYMBOL_NOT_FOUND", "detail": f"标的 '{symbol}' 无技术指标数据"})
    return _format_technical(row)


@router.post("/intraday/{symbol}")
async def get_intraday(symbol: str, days: int = Query(1, ge=1, le=5)) -> dict:
    result = await _service.collect_intraday(symbol, days=days)
    if result is None:
        raise HTTPException(status_code=502, detail={"error": "COLLECT_FAILED", "detail": f"标的 '{symbol}' 分时数据采集失败"})
    return {"symbol": symbol, "items": result}


@router.post("/shareholder/{symbol}")
async def get_shareholder(symbol: str) -> dict:
    result = await _service.collect_shareholder(symbol)
    if result is None:
        raise HTTPException(status_code=502, detail={"error": "COLLECT_FAILED", "detail": f"标的 '{symbol}' 股东结构数据采集失败"})
    return result


@router.post("/dividend/{symbol}")
async def get_dividend(symbol: str) -> dict:
    items = await _service.collect_dividend(symbol)
    if items is None:
        raise HTTPException(status_code=502, detail={"error": "COLLECT_FAILED", "detail": f"标的 '{symbol}' 分红数据采集失败"})
    return {"symbol": symbol, "items": items}


@router.post("/reserve/{symbol}")
async def get_reserve(symbol: str) -> dict:
    result = await _service.collect_reserve(symbol)
    if result is None:
        raise HTTPException(status_code=502, detail={"error": "COLLECT_FAILED", "detail": f"标的 '{symbol}' 业绩预告采集失败"})
    return result

