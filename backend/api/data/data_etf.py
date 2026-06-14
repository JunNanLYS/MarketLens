"""Router for etf (ETF 基础/持仓/净值/持有人/财务) endpoints of /api/v1/data."""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.data._service import _get_service
from backend.api.neodata import verify_api_key


router = APIRouter()
@router.get("/etf/{symbol}")
def get_etf_basic(symbol: str) -> dict:
    """查询 ETF 基本信息（最新一条）。"""
    row = _get_service().get_etf_basic(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无基本信息数据"},
        )
    return row


@router.get("/etf/{symbol}/holdings")
def get_etf_holdings(symbol: str, limit: int = Query(50, ge=1, le=200)) -> dict:
    """查询 ETF 成分股（最新清单）。"""
    items = _get_service().get_etf_holdings(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无成分股数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/etf/{symbol}/nav")
def get_etf_nav(
    symbol: str,
    limit: int = Query(60, ge=1, le=365),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None, alias="to"),
) -> dict:
    """查询 ETF 历史净值。"""
    items = _get_service().get_etf_nav(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无净值数据"},
        )
    # 可选日期范围过滤（在内存中做，因 rows 已 LIMIT 限定）
    if from_ is not None:
        from_str = from_.isoformat()
        items = [it for it in items if it.get("date", "") >= from_str]
    if to is not None:
        to_str = to.isoformat()
        items = [it for it in items if it.get("date", "") <= to_str]
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/etf/{symbol}/holders")
def get_etf_holders(symbol: str) -> dict:
    """查询 ETF 持有人结构（最新一条）。"""
    row = _get_service().get_etf_holders(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无持有人数据"},
        )
    return row


@router.get("/etf/{symbol}/financial")
def get_etf_financial(symbol: str) -> dict:
    """查询 ETF 资产配置（最新一条）。"""
    row = _get_service().get_etf_financial(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无资产配置数据"},
        )
    return row


@router.post("/etf-refresh/{symbol}")
async def refresh_etf(
    symbol: str,
    start: str = Query(..., description="净值起始日期 YYYY-MM-DD"),
    end: str = Query(..., description="净值结束日期 YYYY-MM-DD"),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发 ETF 全套数据采集（5 类）并落库。

    5 个 collect_etf_* 并发执行（asyncio.gather），任一失败不影响其它。
    返回每个分类的 success/failed 计数。
    """
    results = await asyncio.gather(
        _get_service().collect_etf_info(symbol),
        _get_service().collect_etf_holdings(symbol),
        _get_service().collect_etf_nav(symbol, start, end),
        _get_service().collect_etf_holders(symbol),
        _get_service().collect_etf_financial(symbol),
        return_exceptions=True,
    )
    keys = ["info", "holdings", "nav", "holders", "financial"]
    summary: dict[str, dict] = {}
    for k, r in zip(keys, results, strict=True):
        if isinstance(r, Exception):
            summary[k] = {"success": False, "error": str(r)}
        else:
            summary[k] = {"success": r is not None, "items": r}
    return {"symbol": symbol, "summary": summary, "start": start, "end": end}


# ============================================================================
# 阶段 8 修正：板块首页（2 GET 查询 + 1 POST refresh）
# sector_daily_quote 表——行业/概念涨幅榜 + 资金流入 + 热门板块
# ============================================================================


