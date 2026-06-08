import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.neodata import verify_api_key
from backend.services.collection_service import CollectionService

router = APIRouter(prefix="/api/v1/data", tags=["data"])
_service = CollectionService()


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


@router.get("/quotes/{symbol}")
def get_quote(symbol: str) -> dict:
    quote = _service.get_quote(symbol)
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
    result = await _service.collect_quote_single(symbol)
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
    items = _service.get_quote_history(
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
    items = _service.get_kline(
        symbol, limit=limit, from_date=from_date, to_date=to_date
    )
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
        raise HTTPException(
            status_code=404,
            detail={
                "error": "SYMBOL_NOT_FOUND",
                "detail": f"标的 '{symbol}' 无技术指标数据",
            },
        )
    return _format_technical(row)


@router.post("/intraday/{symbol}")
async def get_intraday(
    symbol: str,
    days: int = Query(1, ge=1, le=5),
    _auth: None = Depends(verify_api_key),
) -> dict:
    result = await _service.collect_intraday(symbol, days=days)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 '{symbol}' 分时数据采集失败",
            },
        )
    return {"symbol": symbol, "items": result}


@router.post("/shareholder/{symbol}")
async def get_shareholder(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    result = await _service.collect_shareholder(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 '{symbol}' 股东结构数据采集失败",
            },
        )
    return result


@router.post("/dividend/{symbol}")
async def get_dividend(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    items = await _service.collect_dividend(symbol)
    if items is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 '{symbol}' 分红数据采集失败",
            },
        )
    return {"symbol": symbol, "items": items}


@router.post("/reserve/{symbol}")
async def get_reserve(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    result = await _service.collect_reserve(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 '{symbol}' 业绩预告采集失败",
            },
        )
    return result


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
    items = _service.get_dividends(symbol, limit=limit, source=source)
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
    result = _service.get_shareholders(symbol, limit=limit, source=source)
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
    items = _service.get_profit_forecasts(symbol, limit=limit, source=source)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"标的 {symbol} 无业绩预告数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


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
    items = _service.get_minute_klines(
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


@router.post("/dividend/{symbol}/refresh")
async def refresh_dividend(
    symbol: str,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发分红数据采集并落库。"""
    items = await _service.collect_dividend(symbol)
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
    result = await _service.collect_shareholder(symbol)
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
    result = await _service.collect_reserve(symbol)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COLLECT_FAILED",
                "detail": f"标的 {symbol} 业绩预告采集失败",
            },
        )
    return result


@router.post("/minute/{symbol}/refresh")
async def refresh_minute(
    symbol: str,
    days: int = Query(1, ge=1, le=5),
    _auth: None = Depends(verify_api_key),
) -> dict:
    """手动触发分时数据采集并落库。"""
    items = await _service.collect_intraday(symbol, days=days)
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


@router.get("/etf/{symbol}")
def get_etf_basic(symbol: str) -> dict:
    """查询 ETF 基本信息（最新一条）。"""
    row = _service.get_etf_basic(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无基本信息数据"},
        )
    return row


@router.get("/etf/{symbol}/holdings")
def get_etf_holdings(symbol: str, limit: int = Query(50, ge=1, le=200)) -> dict:
    """查询 ETF 成分股（最新清单）。"""
    items = _service.get_etf_holdings(symbol, limit=limit)
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
    items = _service.get_etf_nav(symbol, limit=limit)
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
    row = _service.get_etf_holders(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"ETF {symbol} 无持有人数据"},
        )
    return row


@router.get("/etf/{symbol}/financial")
def get_etf_financial(symbol: str) -> dict:
    """查询 ETF 资产配置（最新一条）。"""
    row = _service.get_etf_financial(symbol)
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
        _service.collect_etf_info(symbol),
        _service.collect_etf_holdings(symbol),
        _service.collect_etf_nav(symbol, start, end),
        _service.collect_etf_holders(symbol),
        _service.collect_etf_financial(symbol),
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
    items = _service.get_sector_quotes(
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
    items = _service.get_sector_quotes(limit=limit)
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
        _service.collect_sector_board(),
        _service.collect_sector_hot(limit=hot_limit),
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


@router.get("/finance/us/{symbol}")
def get_us_finance(
    symbol: str,
    period_type: str | None = Query(
        None, description="annual | quarter，None 时返回所有"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """查询美股财务（us_financials 表）。"""
    items = _service.get_us_financials(symbol, period_type=period_type, limit=limit)
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
    items = _service.get_us_financials(symbol, period_type=period_type, limit=limit)
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


# 财务采集路由表：symbol 前缀 → 采集方法（lambda 包装 _service 实例方法，
# 避免直接引用 unbound method 导致 self 缺失）。扩展新市场（如 jp/uk）时只需追加一行。
def _collect_us(symbol: str, num: int) -> object:
    return _service.collect_us_finance(symbol, num=num)


def _collect_hk(symbol: str, num: int) -> object:
    return _service.collect_hk_finance(symbol, num=num)


_FINANCE_DISPATCH: dict[str, object] = {
    "us": _collect_us,
    "hk": _collect_hk,
}


# ============================================================================
# 阶段 16：港美 ipo + exdiv 日历（2 GET 查询 + 1 POST refresh）
# 走 /calendar/{event_type} + /calendar-refresh
# A 股 ipo/exdiv 数据源死，仅 hk/us
# ============================================================================


@router.get("/calendar/ipo")
def get_ipo_calendar(
    market: str = Query("hk", description="hk | us，A 股数据源死"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """查询新股日历（落库后的港美新股）。"""
    items = _service.get_ipo_exdiv_calendar(
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
    items = _service.get_ipo_exdiv_calendar(event_type="exdiv", symbol=symbol, limit=50)
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
        _service.collect_ipo_calendar(market),
        _service.collect_exdiv_calendar(exdiv_symbol) if exdiv_symbol else _noop(),
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
    items = _service.get_chip_distribution(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无筹码数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/margintrade/{symbol}")
def get_margintrade(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询融资融券。"""
    items = _service.get_margintrade(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无融资融券数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/blocktrade/{symbol}")
def get_blocktrade(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询大宗交易。"""
    items = _service.get_blocktrade(symbol, limit=limit)
    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "detail": f"{symbol} 无大宗交易数据"},
        )
    return {"symbol": symbol, "items": items, "total": len(items)}


@router.get("/lhb/{symbol}")
def get_lhb(symbol: str, limit: int = Query(20, ge=1, le=200)) -> dict:
    """查询龙虎榜。"""
    items = _service.get_lhb(symbol, limit=limit)
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
        _service.collect_chip_distribution(symbol),
        _service.collect_margintrade(symbol),
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
    result = await _service.collect_blocktrade(symbol, date)
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
    result = await _service.collect_lhb(symbol, date)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={"error": "COLLECT_FAILED", "detail": f"{symbol} 龙虎榜采集失败"},
        )
    return {"symbol": symbol, "date": date, "data": result}
