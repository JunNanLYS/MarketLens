import os
from typing import Any

import httpx
import streamlit as st

_BASE_URL: str = os.environ.get("MARKETLENS_API_URL", "http://localhost:8000/api/v1")

# 分层超时：健康检查快速失败；常规 API 中等；live 端点（触发 westock CLI）允许更久
_TIMEOUT_HEALTH: float = 5.0
_TIMEOUT_API: float = 10.0
_TIMEOUT_LIVE: float = 30.0


@st.cache_resource
def _get_client() -> httpx.Client:
    """共享 httpx 同步客户端。

    注意：Streamlit 是单线程同步框架，httpx.Client.get 是阻塞调用。
    当前架构下无法完全避免阻塞（Streamlit 不支持原生 async UI），但：
    - 通过 @st.cache_resource 复用连接池，避免每次重建 TCP/TLS
    - 调用方应在外部加 @st.cache_data(ttl=N) 控制刷新频率
    - 真正耗时的端点（intraday/shareholder 等）应迁移到后端 GET + 缓存
    """
    return httpx.Client(base_url=_BASE_URL, timeout=_TIMEOUT_API)


def _handle_response(response: httpx.Response) -> dict[str, Any] | list[Any]:
    if response.status_code == 204:
        return {}
    if 200 <= response.status_code < 300:
        return response.json()
    try:
        error_data: dict[str, Any] = response.json()
    except Exception:
        error_data = {"error": "UNKNOWN", "detail": response.text}
    st.error(f"请求失败: {error_data.get('detail', error_data.get('error', '未知错误'))}")
    return error_data


def check_health() -> bool:
    try:
        client: httpx.Client = _get_client()
        resp: httpx.Response = client.get("/health", timeout=_TIMEOUT_HEALTH)
        return resp.status_code == 200
    except Exception:
        return False


def get_data_sources_config() -> dict[str, Any]:
    """查询所有数据源的基础配置（GET /data-sources/config）。

    返回 ``{"structured": [...], "news": [...]}``;每项包含
    ``name`` / ``provider`` / ``type`` / ``enabled`` / ``optional`` / ``timeout``。
    不探测 token 健康度,适合 UI 高频刷新场景。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/data-sources/config")
    return _handle_response(resp)


def get_assets(**params: Any) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/assets", params=params)
    return _handle_response(resp)


def get_asset(asset_id: int) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/assets/{asset_id}")
    return _handle_response(resp)


def create_asset(data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post("/assets", json=data)
    return _handle_response(resp)


def update_asset(asset_id: int, data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.patch(f"/assets/{asset_id}", json=data)
    return _handle_response(resp)


def delete_asset(asset_id: int) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.delete(f"/assets/{asset_id}")
    return _handle_response(resp)


def search_assets(keyword: str, market: str | None = None) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    payload: dict[str, Any] = {"keyword": keyword}
    if market:
        payload["market"] = market
    resp: httpx.Response = client.get("/assets/search", params=payload)
    return _handle_response(resp)


def get_quote(symbol: str) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/quotes/{symbol}")
    return _handle_response(resp)


def get_kline(symbol: str, limit: int = 60) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/kline/{symbol}", params={"limit": limit})
    return _handle_response(resp)


def get_finance(symbol: str, limit: int = 4) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/finance/{symbol}", params={"limit": limit})
    return _handle_response(resp)


def get_fund_flow(symbol: str, days: int = 5) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/fund-flow/{symbol}", params={"days": days})
    return _handle_response(resp)


def get_technical(symbol: str) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/technical/{symbol}")
    return _handle_response(resp)


def get_reports(**params: Any) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/reports", params=params)
    return _handle_response(resp)


def get_latest_report(symbol: str) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/reports/{symbol}")
    return _handle_response(resp)


def generate_reports(symbols: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    payload: dict[str, Any] = {"force": force}
    if symbols:
        payload["symbols"] = symbols
    resp: httpx.Response = client.post("/reports/generate", json=payload, timeout=_TIMEOUT_LIVE)
    return _handle_response(resp)


def get_accounts(include_deleted: bool = False) -> list[dict[str, Any]]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/accounts", params={"include_deleted": include_deleted})
    return _handle_response(resp)


def create_account(data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post("/accounts", json=data)
    return _handle_response(resp)


def update_account(account_id: int, data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.patch(f"/accounts/{account_id}", json=data)
    return _handle_response(resp)


def delete_account(account_id: int) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.delete(f"/accounts/{account_id}")
    return _handle_response(resp)


def get_transactions(**params: Any) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/transactions", params=params)
    return _handle_response(resp)


def create_transaction(data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post("/transactions", json=data)
    return _handle_response(resp)


def delete_transaction(transaction_id: int) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.delete(f"/transactions/{transaction_id}")
    return _handle_response(resp)


def get_positions(account_id: int | None = None) -> list[dict[str, Any]]:
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {}
    if account_id is not None:
        params["account_id"] = account_id
    resp: httpx.Response = client.get("/positions", params=params)
    return _handle_response(resp)


def get_realized_pnl(account_id: int | None = None, symbol: str | None = None) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {}
    if account_id is not None:
        params["account_id"] = account_id
    if symbol is not None:
        params["symbol"] = symbol
    resp: httpx.Response = client.get("/positions/realized-pnl", params=params)
    return _handle_response(resp)


def get_task_status() -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/tasks/status")
    return _handle_response(resp)


def get_intraday(symbol: str, days: int = 1) -> dict[str, Any]:
    """实时采集分时——会触发 westock CLI subprocess。

    UI 层应使用 @st.cache_data(ttl=300) 包装以避免重复触发。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/intraday/{symbol}", params={"days": days}, timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_shareholder(symbol: str) -> dict[str, Any]:
    """实时采集股东结构——会触发 westock CLI subprocess。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/shareholder/{symbol}", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_reserve(symbol: str) -> dict[str, Any]:
    """实时采集业绩预告——会触发 westock CLI subprocess。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/reserve/{symbol}", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_dividend(symbol: str) -> dict[str, Any]:
    """实时采集分红记录——会触发 westock CLI subprocess。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/dividend/{symbol}", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_etf_info(symbol: str) -> dict[str, Any]:
    """查询 ETF 基本信息（GET /data/etf/{symbol}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/etf/{symbol}")
    return _handle_response(resp)


def get_etf_holdings(symbol: str, limit: int = 50) -> dict[str, Any]:
    """查询 ETF 成分股（GET /data/etf/{symbol}/holdings）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(
        f"/data/etf/{symbol}/holdings", params={"limit": limit}
    )
    return _handle_response(resp)


def get_etf_nav(symbol: str, limit: int = 60) -> dict[str, Any]:
    """查询 ETF 历史净值（GET /data/etf/{symbol}/nav）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(
        f"/data/etf/{symbol}/nav", params={"limit": limit}
    )
    return _handle_response(resp)


def get_sectors_board(limit: int = 50) -> dict[str, Any]:
    """查询板块首页数据（GET /data/sectors/board）。

    返回行业/概念/资金流入涨幅榜混合列表。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/data/sectors/board", params={"limit": limit})
    return _handle_response(resp)


def get_sectors_hot(limit: int = 10) -> dict[str, Any]:
    """查询热门板块（GET /data/sectors/hot）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/data/sectors/hot", params={"limit": limit})
    return _handle_response(resp)


def get_ipo_calendar(market: str = "hk", limit: int = 50) -> dict[str, Any]:
    """查询港美 IPO 日历（GET /data/calendar/ipo）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(
        "/data/calendar/ipo", params={"market": market, "limit": limit}
    )
    return _handle_response(resp)


def get_exdiv_calendar(symbol: str) -> dict[str, Any]:
    """查询标的除权日历（GET /data/calendar/exdiv/{symbol}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/calendar/exdiv/{symbol}")
    return _handle_response(resp)


def get_chip(symbol: str, limit: int = 20) -> dict[str, Any]:
    """查询筹码成本分布（GET /data/chip/{symbol}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/chip/{symbol}", params={"limit": limit})
    return _handle_response(resp)


def get_news(**params: Any) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/news", params=params)
    return _handle_response(resp)


def get_news_detail(news_id: int) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/news/{news_id}")
    return _handle_response(resp)


def get_task_logs(**params: Any) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/tasks/logs", params=params)
    return _handle_response(resp)


def trigger_task(task_name: str) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/tasks/trigger/{task_name}", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def update_transaction(transaction_id: int, data: dict[str, Any]) -> dict[str, Any]:
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.patch(f"/transactions/{transaction_id}", json=data)
    return _handle_response(resp)


# ============================================================================
# 阶段 8 审查补全：以下 30 个 client 方法对应 backend/api/ 中已存在但
# 此前无 client 包装的端点。命名规则：与 backend 端点函数名 1:1 对应
# （如 get_etf_holders / refresh_dividend）。所有 refresh 端点统一使用
# _TIMEOUT_LIVE（westock CLI subprocess）；所有 GET 查询端点使用默认超时。
# ============================================================================


def get_account(account_id: int) -> dict[str, Any]:
    """查询单账户详情（GET /accounts/{account_id}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/accounts/{account_id}")
    return _handle_response(resp)


def get_transaction(transaction_id: int) -> dict[str, Any]:
    """查询单笔交易详情（GET /transactions/{transaction_id}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/transactions/{transaction_id}")
    return _handle_response(resp)


def refresh_quote(symbol: str) -> dict[str, Any]:
    """手动触发单标行情刷新（POST /data/quotes/{symbol}/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/quotes/{symbol}/refresh", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_quote_history(
    symbol: str,
    limit: int = 100,
    from_: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """查询标的历史行情（GET /data/quotes/{symbol}/history）。

    ``from_`` / ``to`` 为 ISO 8601 时间字符串。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    resp: httpx.Response = client.get(
        f"/data/quotes/{symbol}/history", params=params
    )
    return _handle_response(resp)


def get_dividend_records(
    symbol: str, limit: int = 20, source: str | None = None
) -> dict[str, Any]:
    """查询分红记录（GET /data/dividend/{symbol}，已落库数据）。

    注意：与 POST /data/dividend/{symbol}（实时采集）路径相同但方法不同。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if source:
        params["source"] = source
    resp: httpx.Response = client.get(f"/data/dividend/{symbol}", params=params)
    return _handle_response(resp)


def get_shareholder_records(
    symbol: str, limit: int = 10, source: str | None = None
) -> dict[str, Any]:
    """查询股东结构（GET /data/shareholder/{symbol}，top + 户数历史）。

    注意：与 POST /data/shareholder/{symbol}（实时采集）路径相同但方法不同。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if source:
        params["source"] = source
    resp: httpx.Response = client.get(f"/data/shareholder/{symbol}", params=params)
    return _handle_response(resp)


def get_reserve_records(
    symbol: str, limit: int = 20, source: str | None = None
) -> dict[str, Any]:
    """查询业绩预告（GET /data/reserve/{symbol}，按 report_period 降序）。

    注意：与 POST /data/reserve/{symbol}（实时采集）路径相同但方法不同。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if source:
        params["source"] = source
    resp: httpx.Response = client.get(f"/data/reserve/{symbol}", params=params)
    return _handle_response(resp)


def get_minute_klines(
    symbol: str,
    limit: int = 240,
    from_: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """查询分时 K 线（GET /data/minute/{symbol}，按 time 降序）。"""
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    resp: httpx.Response = client.get(f"/data/minute/{symbol}", params=params)
    return _handle_response(resp)


def refresh_dividend(symbol: str) -> dict[str, Any]:
    """手动触发分红数据采集并落库（POST /data/dividend/{symbol}/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/dividend/{symbol}/refresh", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def refresh_shareholder(symbol: str) -> dict[str, Any]:
    """手动触发股东结构采集并落库（POST /data/shareholder/{symbol}/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/shareholder/{symbol}/refresh", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def refresh_reserve(symbol: str) -> dict[str, Any]:
    """手动触发业绩预告采集并落库（POST /data/reserve/{symbol}/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/reserve/{symbol}/refresh", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def refresh_minute(symbol: str, days: int = 1) -> dict[str, Any]:
    """手动触发分时数据采集并落库（POST /data/minute/{symbol}/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/minute/{symbol}/refresh",
        params={"days": days},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def get_etf_holders(symbol: str) -> dict[str, Any]:
    """查询 ETF 持有人结构（GET /data/etf/{symbol}/holders）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/etf/{symbol}/holders")
    return _handle_response(resp)


def get_etf_financial(symbol: str) -> dict[str, Any]:
    """查询 ETF 资产配置（GET /data/etf/{symbol}/financial）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/etf/{symbol}/financial")
    return _handle_response(resp)


def refresh_etf(symbol: str, start: str, end: str) -> dict[str, Any]:
    """手动触发 ETF 全套数据采集（5 类）并落库（POST /data/etf-refresh/{symbol}）。

    ``start`` / ``end`` 为 YYYY-MM-DD 净值起止日期。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/etf-refresh/{symbol}",
        params={"start": start, "end": end},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def refresh_sectors(hot_limit: int = 10) -> dict[str, Any]:
    """手动触发板块首页 + 热门板块采集并落库（POST /data/sectors/refresh）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        "/data/sectors/refresh",
        params={"hot_limit": hot_limit},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def get_us_finance(
    symbol: str, period_type: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """查询美股财务（GET /data/finance/us/{symbol}）。

    ``period_type`` 可选 ``annual`` / ``quarter``；None 时返回所有。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if period_type:
        params["period_type"] = period_type
    resp: httpx.Response = client.get(f"/data/finance/us/{symbol}", params=params)
    return _handle_response(resp)


def get_hk_finance(
    symbol: str, period_type: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """查询港股财务（GET /data/finance/hk/{symbol}）。

    ``period_type`` 可选 ``annual`` / ``quarter``；None 时返回所有。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if period_type:
        params["period_type"] = period_type
    resp: httpx.Response = client.get(f"/data/finance/hk/{symbol}", params=params)
    return _handle_response(resp)


def refresh_finance(symbol: str, num: int = 4) -> dict[str, Any]:
    """手动触发港美股财务采集并落库（POST /data/finance-refresh/{symbol}）。

    根据 symbol 前缀自动选 us_finance / hk_finance。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/finance-refresh/{symbol}",
        params={"num": num},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def refresh_calendar(market: str = "hk", exdiv_symbol: str | None = None) -> dict[str, Any]:
    """手动触发港美新股日历（ipo）+ 除权日历（exdiv）采集并落库。

    ``exdiv_symbol`` 为 None 时跳过 exdiv 采集。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"market": market}
    if exdiv_symbol:
        params["exdiv_symbol"] = exdiv_symbol
    resp: httpx.Response = client.post(
        "/data/calendar-refresh", params=params, timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def get_margintrade(symbol: str, limit: int = 20) -> dict[str, Any]:
    """查询融资融券（GET /data/margintrade/{symbol}，A 股）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(
        f"/data/margintrade/{symbol}", params={"limit": limit}
    )
    return _handle_response(resp)


def get_blocktrade(symbol: str, limit: int = 20) -> dict[str, Any]:
    """查询大宗交易（GET /data/blocktrade/{symbol}，A 股）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(
        f"/data/blocktrade/{symbol}", params={"limit": limit}
    )
    return _handle_response(resp)


def get_lhb(symbol: str, limit: int = 20) -> dict[str, Any]:
    """查询龙虎榜（GET /data/lhb/{symbol}，A 股）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get(f"/data/lhb/{symbol}", params={"limit": limit})
    return _handle_response(resp)


def refresh_chip_margintrade(symbol: str) -> dict[str, Any]:
    """手动触发筹码 + 融资融券采集并落库（POST /data/chip-refresh/{symbol}）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/chip-refresh/{symbol}", timeout=_TIMEOUT_LIVE
    )
    return _handle_response(resp)


def refresh_blocktrade(symbol: str, date: str) -> dict[str, Any]:
    """手动触发大宗交易采集（POST /data/blocktrade-refresh/{symbol}）。

    ``date`` 为 YYYY-MM-DD。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/blocktrade-refresh/{symbol}",
        params={"date": date},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def refresh_lhb(symbol: str, date: str) -> dict[str, Any]:
    """手动触发龙虎榜采集（POST /data/lhb-refresh/{symbol}）。

    ``date`` 为 YYYY-MM-DD。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post(
        f"/data/lhb-refresh/{symbol}",
        params={"date": date},
        timeout=_TIMEOUT_LIVE,
    )
    return _handle_response(resp)


def get_data_sources_status() -> dict[str, Any]:
    """查询所有数据源的配置与健康状态（GET /data-sources/status）。

    与 /data-sources/config 的区别：本端点会读 token 状态、解析 command 路径，
    不适合 UI 高频刷新；用于运维诊断场景。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/data-sources/status")
    return _handle_response(resp)


def get_neodata_token_status() -> dict[str, Any]:
    """查询 NeoData token 状态（GET /neodata/token-status，不暴露过期时间）。"""
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.get("/neodata/token-status")
    return _handle_response(resp)


def save_neodata_token(token: str) -> dict[str, Any]:
    """保存 NeoData token（POST /neodata/token，JSON body）。

    该端点为写端点，后端会校验 API Key（X-API-Key header）。
    """
    client: httpx.Client = _get_client()
    resp: httpx.Response = client.post("/neodata/token", json={"token": token})
    return _handle_response(resp)


def get_report_history(
    symbol: str,
    limit: int = 30,
    from_: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """查询 AI 报告历史（GET /reports/{symbol}/history）。

    ``from_`` / ``to`` 为 ISO 8601 日期字符串（YYYY-MM-DD）。
    """
    client: httpx.Client = _get_client()
    params: dict[str, Any] = {"limit": limit}
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    resp: httpx.Response = client.get(f"/reports/{symbol}/history", params=params)
    return _handle_response(resp)