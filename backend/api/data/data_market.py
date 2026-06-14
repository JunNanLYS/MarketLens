"""Router for market (板块 + 日历 + 筹码 + 融资融券 + 大宗交易 + 龙虎榜) endpoints of /api/v1/data."""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.data._service import _get_service
from backend.api.neodata import verify_api_key


router = APIRouter()
@router.get("/sectors/board")
def get_sector_board(
    sector_type: str | None = Query(
        None, description="industry | concept | fund_flow，None 时返回所有"
    ),
    date: date | None = Query(None, description="YYYY-MM-DD，None 时取最新"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """查询板块首页数据（行业/概念涨幅榜 + 行业资金流入 Top5）。"""
    date_str = date.isoformat() if date is not None else None
    items = _get_service().get_sector_quotes(
        sector_type=sector_type, date=date_str, limit=limit
    )
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": "无板块首页数据"},
        )
    return {
        "items": items,
        "total": len(items),
        "sector_type": sector_type,
        "date": date_str,
    }


@router.get("/sectors/hot")
def get_sector_hot(
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    """查询热门板块（落库后的最近榜单）。

    注：本端点读取已落库数据；首次访问前需 POST /sectors/refresh 触发采集。
    """
    items = _get_service().get_sector_quotes(limit=limit)
    # 简单过滤：取 rank 非空的行（即 hot 落库的）
    hot_items = [it for it in items if it.get("rank") is not None]
    if not hot_items:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_DATA",
                "detail": "无热门板块数据，请先调用 POST /sectors/refresh",
            },
        )
    return {"items": hot_items, "total": len(hot_items)}


@router.post("/sectors/refresh")
async def refresh_sectors(
    hot_limit: int = Query(10, ge=1, le=50),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发板块首页 + 热门板块 采集并落库。

    两个 collect 并发执行（asyncio.gather），任一失败不影响其它。
    """
    results = await asyncio.gather(
        _get_service().collect_sector_board(),
        _get_service().collect_sector_hot(limit=hot_limit),
        return_exceptions=True,
    )
    summary: dict[str, dict] = {}
    keys = ["board", "hot"]
    for k, r in zip(keys, results, strict=True):
        if isinstance(r, Exception):
            summary[k] = {"success": False, "error": str(r)}
        else:
            if isinstance(r, list):
                summary[k] = {"success": True, "items": len(r)}
            else:
                summary[k] = {"success": r is not None}
    return {"summary": summary, "hot_limit": hot_limit}


# ============================================================================
# 阶段 15：港美股财务（2 GET 查询 + 1 POST refresh）
# 走 /finance/us/{symbol} / /finance/hk/{symbol} / /finance-refresh/{symbol}
# ============================================================================


@router.get("/calendar/ipo")
def get_ipo_calendar(
    market: str = Query("hk", description="hk | us，A 股数据源死"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """查询新股日历（落库后的港美新股）。"""
    items = _get_service().get_ipo_exdiv_calendar(
        event_type="ipo", market=market, limit=limit
    )
    if not items:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_DATA",
                "detail": f"{market} 市场无新股日历数据，请先 POST /calendar-refresh",
            },
        )
    return {"items": items, "total": len(items), "market": market}


@router.get("/calendar/exdiv/{symbol}")
def get_exdiv_calendar(symbol: str) -> dict:
    """查询单只股票的除权日历（港美）。"""
    items = _get_service().get_ipo_exdiv_calendar(event_type="exdiv", symbol=symbol, limit=50)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_DATA",
                "detail": f"{symbol} 无除权数据，请先 POST /calendar-refresh",
            },
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/calendar-refresh")
async def refresh_calendar(
    market: str = Query("hk", description="hk | us"),
    exdiv_symbol: str | None = Query(
        None, description="exdiv 采集的股票代码（不填则跳过 exdiv）"
    ),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发新股日历（ipo）+ 除权日历（exdiv）采集并落库。

    两个 collect 并发（asyncio.gather），任一失败不影响其它。
    """
    results = await asyncio.gather(
        _get_service().collect_ipo_calendar(market),
        _get_service().collect_exdiv_calendar(exdiv_symbol) if exdiv_symbol else _noop(),
        return_exceptions=True,
    )
    summary: dict[str, dict] = {}
    keys = ["ipo", "exdiv"]
    for k, r in zip(keys, results, strict=True):
        if isinstance(r, Exception):
            summary[k] = {"success": False, "error": str(r)}
        elif r is None:
            summary[k] = {"success": False, "error": "no data (or skipped)"}
        elif isinstance(r, list):
            summary[k] = {"success": True, "items": len(r)}
        else:
            summary[k] = {"success": True}
    return {"summary": summary, "market": market, "exdiv_symbol": exdiv_symbol}


async def _noop() -> None:
    """占位 noop（asyncio.gather 需要可 await 对象）。"""
    return None


# ============================================================================
# 阶段 17：筹码 / 融资融券 / 大宗 / 龙虎榜（4 GET 查询 + 1 POST refresh）
# 4 个维度都仅 A 股支持；blocktrade/lhb 需指定日期
# ============================================================================


@router.get("/chip/{symbol}")
def get_chip(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询筹码成本分布。"""
    items = _get_service().get_chip_distribution(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无筹码数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/margintrade/{symbol}")
def get_margintrade(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询融资融券。"""
    items = _get_service().get_margintrade(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无融资融券数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/blocktrade/{symbol}")
def get_blocktrade(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询大宗交易。"""
    items = _get_service().get_blocktrade(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无大宗交易数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/lhb/{symbol}")
def get_lhb(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询龙虎榜。"""
    items = _get_service().get_lhb(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无龙虎榜数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/chip-refresh/{symbol}")
async def refresh_chip_margintrade(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发筹码 + 融资融券采集（同一 refresh，无日期参数）。"""
    results = await asyncio.gather(
        _get_service().collect_chip_distribution(symbol),
        _get_service().collect_margintrade(symbol),
        return_exceptions=True,
    )
    keys = ["chip", "margintrade"]
    summary: dict[str, dict] = {}
    for k, r in zip(keys, results, strict=True):
        if isinstance(r, Exception):
            summary[k] = {"success": False, "error": str(r)}
        else:
            summary[k] = {"success": r is not None}
    return {"symbol": symbol, "summary": summary}


@router.post("/blocktrade-refresh/{symbol}")
async def refresh_blocktrade(
    symbol: str,
    date: str = Query(..., description="YYYY-MM-DD"),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发大宗交易采集（单只 + 指定日期）。"""
    result = await _get_service().collect_blocktrade(symbol, date)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={"error": "COLLECT_FAILED", "detail": f"{symbol} 大宗交易采集失败"},
        )
    return {"symbol": symbol, "date": date, "data": result}


@router.post("/lhb-refresh/{symbol}")
async def refresh_lhb(
    symbol: str,
    date: str = Query(..., description="YYYY-MM-DD"),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发龙虎榜采集（单只 + 指定日期）。"""
    result = await _get_service().collect_lhb(symbol, date)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={"error": "COLLECT_FAILED", "detail": f"{symbol} 龙虎榜采集失败"},
        )
    return {"symbol": symbol, "date": date, "data": result}
async def _noop() -> None:
    """占位 noop（asyncio.gather 需要可 await 对象）。"""
    return None


# ============================================================================
# 阶段 17：筹码 / 融资融券 / 大宗 / 龙虎榜（4 GET 查询 + 1 POST refresh）
# 4 个维度都仅 A 股支持；blocktrade/lhb 需指定日期
# ============================================================================


