import os
from typing import Any

import httpx
import streamlit as st

_BASE_URL: str = os.environ.get("MARKETLENS_API_URL", "http://localhost:8000/api/v1")


def _get_client() -> httpx.Client:
    if "http_client" not in st.session_state:
        st.session_state.http_client = httpx.Client(base_url=_BASE_URL, timeout=30.0)
    return st.session_state.http_client


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
        resp: httpx.Response = client.get("/health", timeout=5.0)
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
    resp: httpx.Response = client.post("/reports/generate", json=payload)
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
