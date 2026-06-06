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


def get_realized_pnl(account_id: int | None = None, symbol: str | None = None) -> list[dict[str, Any]]:
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