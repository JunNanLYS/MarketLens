"""Router for finance (财务 + 资金流 + 技术 + 股东 + 分红 + 业绩预告 + 美港股) endpoints of /api/v1/data."""


from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.data._service import _get_service
from backend.api.dependencies import verify_api_key


router = APIRouter()


def _format_technical(row: dict) -> dict:
    return {
        "symbol": row.get("symbol"),
        "date": row.get("date"),
        "ma": {
            "ma5": row.get("ma5"),
            "ma10": row.get("ma10"),
            "ma20": row.get("ma20"),
            "ma60": row.get("ma60"),
        },
        "macd": {
            "dif": row.get("macd_dif"),
            "dea": row.get("macd_dea"),
            "histogram": row.get("macd_histogram"),
        },
        "rsi": {"rsi6": row.get("rsi6"), "rsi14": row.get("rsi14")},
        "boll": {
            "upper": row.get("boll_upper"),
            "middle": row.get("boll_middle"),
            "lower": row.get("boll_lower"),
        },
        "volume_ma": {"ma5": row.get("volume_ma5"), "ma20": row.get("volume_ma20")},
        "source": row.get("source"),
        "collected_at": row.get("collected_at"),
    }


@router.get("/finance/{symbol}")
def get_finance(symbol: str, limit: int = Query(4, ge=1, le=20)) -> dict:
    items = _get_service().get_finance(symbol, limit=limit)
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/fund-flow/{symbol}")
def get_fund_flow(symbol: str, days: int = Query(5, ge=1, le=30)) -> dict:
    result = _get_service().get_fund_flow(symbol, days=days)
    return {"symbol": symbol, "items": result["items"], "summary": result["summary"]}


@router.get("/technical/{symbol}")
def get_technical(symbol: str) -> dict:
    row = _get_service().get_technical(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "SYMBOL_NOT_FOUND",
                "detail": f"标的 '{symbol}' 无技术指标数据",
            },
        )
    return _format_technical(row)


# ============================================================================
# 阶段 3：4 个 GET 查询端点（按需查询已落库数据）
# GET 无副作用；写入/触发采集走 /refresh 端点
# ============================================================================


@router.get("/dividend/{symbol}")
def get_dividend_records(
    symbol: str,
    limit: int = Query(20, ge=1, le=200),
    source: str | None = Query(None, description="按数据源过滤"),
) -> dict:
    """查询分红记录（按 ex_date 降序）。"""
    items = _get_service().get_dividends(symbol, limit=limit, source=source)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"标的 {symbol} 无分红数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/shareholder/{symbol}")
def get_shareholder_records(
    symbol: str,
    limit: int = Query(10, ge=1, le=100),
    source: str | None = Query(None, description="按数据源过滤"),
) -> dict:
    """查询股东结构（top + 户数历史）。"""
    result = _get_service().get_shareholders(symbol, limit=limit, source=source)
    if not result["top_shareholders"] and not result["holder_count_history"]:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"标的 {symbol} 无股东数据"},
        )
    return {
        "symbol": symbol,
        "top_shareholders": result["top_shareholders"],
        "holder_count_history": result["holder_count_history"],
    }


@router.get("/reserve/{symbol}")
def get_reserve_records(
    symbol: str,
    limit: int = Query(20, ge=1, le=200),
    source: str | None = Query(None, description="按数据源过滤"),
) -> dict:
    """查询业绩预告（按 report_period 降序）。"""
    items = _get_service().get_profit_forecasts(symbol, limit=limit, source=source)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"标的 {symbol} 无业绩预告数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/dividend/{symbol}/refresh")
async def refresh_dividend(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发分红数据采集并落库。"""
    items = await _get_service().collect_dividend(symbol)
    if items is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 {symbol} 分红数据采集失败",
            },
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/shareholder/{symbol}/refresh")
async def refresh_shareholder(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发股东结构采集并落库（双表单事务）。"""
    result = await _get_service().collect_shareholder(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 {symbol} 股东结构数据采集失败",
            },
        )
    return result


@router.post("/reserve/{symbol}/refresh")
async def refresh_reserve(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发业绩预告采集并落库。"""
    result = await _get_service().collect_reserve(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 {symbol} 业绩预告采集失败",
            },
        )
    return result


@router.get("/finance/us/{symbol}")
def get_us_finance(
    symbol: str,
    period_type: str | None = Query(
        None, description="annual | quarter，None 时返回所有"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """查询美股财务（us_financials 表）。"""
    items = _get_service().get_us_financials(symbol, period_type=period_type, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"美股 {symbol} 无财务数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/finance/hk/{symbol}")
def get_hk_finance(
    symbol: str,
    period_type: str | None = Query(
        None, description="annual | quarter，None 时返回所有"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """查询港股财务（us_financials 表，currency=HKD 区分）。"""
    items = _get_service().get_us_financials(symbol, period_type=period_type, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"港股 {symbol} 无财务数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.post("/finance-refresh/{symbol}")
async def refresh_finance(
    symbol: str,
    num: int = Query(4, ge=1, le=12),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发港美股财务采集（按 symbol 前缀自动选 us_finance / hk_finance）并落库。

    自动判断：symbol 以 us 开头 → 美股；以 hk 开头 → 港股。
    路由表由 _FINANCE_DISPATCH 维护（避免散落硬编码）。
    """
    collect_fn = _FINANCE_DISPATCH.get(symbol[:2])
    if collect_fn is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_SYMBOL",
                "detail": f"symbol 必须以 us/hk 开头，实际 {symbol}",
            },
        )
    result = await collect_fn(symbol, num=num)
    summary: dict[str, dict] = {}
    if isinstance(result, Exception):
        summary["finance"] = {"success": False, "error": str(result)}
    else:
        summary["finance"] = {
            "success": result is not None,
            "items": len(result) if isinstance(result, list) else 0,
        }
    return {"symbol": symbol, "summary": summary, "num": num}


# 财务采集路由表：symbol 前缀 → 采集方法。扩展新市场（如 jp/uk）时只需追加一行。
# collect_*_finance 是 async（CLAUDE.md 硬约束），包装函数必须 async def + await。
async def _collect_us(symbol: str, num: int) -> object:
    return await _get_service().collect_us_finance(symbol, num=num)


async def _collect_hk(symbol: str, num: int) -> object:
    return await _get_service().collect_hk_finance(symbol, num=num)


_FINANCE_DISPATCH: dict[str, object] = {
    "us": _collect_us,
    "hk": _collect_hk,
}
