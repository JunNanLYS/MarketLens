from typing import Any

import streamlit as st

from ui.api_client import get_assets, create_asset, update_asset, delete_asset, search_assets

MARKET_OPTIONS: dict[str, str] = {
    "全部": "",
    "A 股（上证）": "sh",
    "A 股（深证）": "sz",
    "港股": "hk",
    "美股": "us",
    "期货": "fut",
    "商品期货 (hf)": "hf",
    "金融期货 (nf)": "nf",
}

ASSET_TYPE_OPTIONS: dict[str, str] = {
    "全部": "",
    "股票": "stock",
    "ETF": "etf",
    "指数": "index",
    "期货": "future",
}

STATUS_OPTIONS: dict[str, str | None] = {
    "全部": None,
    "已启用": True,
    "已停用": False,
}


def _format_change_pct(value: float | None) -> str:
    if value is None:
        return "-"
    sign: str = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _render_filters() -> tuple[str, str, str | None]:
    col1, col2, col3 = st.columns(3)
    with col1:
        market_label: str = st.selectbox("市场", list(MARKET_OPTIONS.keys()), key="filter_market")
    with col2:
        type_label: str = st.selectbox("资产类型", list(ASSET_TYPE_OPTIONS.keys()), key="filter_type")
    with col3:
        status_label: str = st.selectbox("状态", list(STATUS_OPTIONS.keys()), key="filter_status")
    return MARKET_OPTIONS[market_label], ASSET_TYPE_OPTIONS[type_label], STATUS_OPTIONS[status_label]


def _render_asset_table(assets: list[dict[str, Any]]) -> None:
    if not assets:
        st.info("暂无追踪标的")
        return

    for asset in assets:
        with st.container():
            cols = st.columns([2, 2, 1, 1, 1.5, 1.5, 1, 2])
            with cols[0]:
                st.markdown(f"**{asset.get('symbol', '')}**")
            with cols[1]:
                st.text(asset.get("name", "-"))
            with cols[2]:
                st.text(asset.get("market", "-").upper())
            with cols[3]:
                st.text(asset.get("asset_type", "-"))
            with cols[4]:
                price: float | None = asset.get("latest_price")
                st.text(f"{price:.2f}" if price is not None else "-")
            with cols[5]:
                change_pct: float | None = asset.get("latest_change_pct")
                formatted: str = _format_change_pct(change_pct)
                if change_pct is not None:
                    color: str = "green" if change_pct > 0 else "red" if change_pct < 0 else "inherit"
                    arrow: str = "▲" if change_pct > 0 else "▼" if change_pct < 0 else ""
                    st.markdown(f":{color}[{arrow} {formatted}]".strip())
                else:
                    st.text("-")
            with cols[6]:
                status: bool = asset.get("enabled", True)
                st.text("启用" if status else "停用")
            with cols[7]:
                asset_id: int = asset["id"]
                btn_cols = st.columns(2)
                with btn_cols[0]:
                    new_status: bool = not status
                    label: str = "停用" if status else "启用"
                    if st.button(label, key=f"toggle_{asset_id}"):
                        result: dict[str, Any] = update_asset(asset_id, {"enabled": new_status})
                        if "error" not in result and "id" in result:
                            st.success(f"已{label}")
                            st.rerun()
                        else:
                            st.error(result.get("detail", "操作失败"))
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_{asset_id}", help="删除该标的"):
                        st.session_state[f"confirm_delete_{asset_id}"] = True
                        st.rerun()

            if st.session_state.get(f"confirm_delete_{asset_id}"):
                st.warning(f"确认删除标的 {asset.get('symbol', '')}？历史数据将保留。")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("确认删除", key=f"confirm_del_{asset_id}"):
                        del_result: dict[str, Any] = delete_asset(asset_id)
                        st.session_state.pop(f"confirm_delete_{asset_id}", None)
                        if "error" not in del_result:
                            st.success("已删除")
                            st.rerun()
                        else:
                            st.error(del_result.get("detail", "删除失败"))
                with c2:
                    if st.button("取消", key=f"cancel_del_{asset_id}"):
                        st.session_state.pop(f"confirm_delete_{asset_id}", None)
                        st.rerun()


def _render_add_form() -> None:
    with st.expander("➕ 添加追踪标的"):
        with st.form("add_asset_form"):
            col1, col2 = st.columns(2)
            with col1:
                symbol: str = st.text_input("标的代码 *", placeholder="如 hk00700")
                name: str = st.text_input("名称（可选）", placeholder="留空自动补全")
            with col2:
                market: str = st.selectbox(
                    "市场",
                    ["自动识别", "sh", "sz", "hk", "us"],
                    key="add_market",
                )
                asset_type: str = st.selectbox(
                    "资产类型",
                    ["stock", "etf", "index", "future"],
                    key="add_asset_type",
                )
            tags_input: str = st.text_input("标签（逗号分隔）", placeholder="如 互联网,港股通")
            notes: str = st.text_area("备注", height=68)
            submitted: bool = st.form_submit_button("添加")
            if submitted:
                if not symbol.strip():
                    st.error("请输入标的代码")
                else:
                    tags_split: list[str] = []
                    if tags_input.strip():
                        tags_split = [t.strip() for t in tags_input.split(",") if t.strip()]
                    if len(tags_split) > 10:
                        st.error("标签数量不能超过 10 个")
                        return
                    if any(len(t) > 20 for t in tags_split):
                        st.error("单个标签长度不能超过 20 个字符")
                        return
                    data: dict[str, Any] = {
                        "symbol": symbol.strip(),
                        "asset_type": asset_type,
                    }
                    if name.strip():
                        data["name"] = name.strip()
                    if market != "自动识别":
                        data["market"] = market
                    if tags_split:
                        data["tags"] = tags_split
                    if notes.strip():
                        data["notes"] = notes.strip()
                    result: dict[str, Any] = create_asset(data)
                    if "id" in result:
                        st.success(f"已添加: {result.get('symbol', symbol)}")
                        st.rerun()
                    else:
                        st.error(result.get("detail", "添加失败"))


def _render_search() -> None:
    with st.expander("🔍 搜索外部标的"):
        col1, col2 = st.columns([3, 1])
        with col1:
            keyword: str = st.text_input("搜索关键词", placeholder="输入代码或名称", key="search_keyword")
        with col2:
            search_market: str = st.selectbox(
                "市场",
                ["全部", "sh", "sz", "hk", "us"],
                key="search_market",
            )
        if st.button("搜索", key="do_search"):
            if not keyword.strip():
                st.warning("请输入搜索关键词")
            else:
                market_param: str | None = search_market if search_market != "全部" else None
                result: dict[str, Any] = search_assets(keyword.strip(), market=market_param)
                items: list[dict[str, Any]] = result.get("items", [])
                if not items:
                    st.info("未找到匹配标的")
                else:
                    for item in items:
                        c1, c2, c3 = st.columns([3, 2, 1])
                        with c1:
                            st.markdown(f"**{item.get('symbol', '')}** — {item.get('name', '')}")
                        with c2:
                            st.text(f"{item.get('market', '').upper()} / {item.get('asset_type', '')}")
                        with c3:
                            if st.button("添加", key=f"search_add_{item.get('symbol', '')}"):
                                add_data: dict[str, Any] = {
                                    "symbol": item["symbol"],
                                    "name": item.get("name"),
                                    "market": item.get("market"),
                                    "asset_type": item.get("asset_type", "stock"),
                                }
                                add_result: dict[str, Any] = create_asset(add_data)
                                if "id" in add_result:
                                    st.success(f"已添加: {item['symbol']}")
                                    st.rerun()
                                else:
                                    st.error(add_result.get("detail", "添加失败"))


def render() -> None:
    st.header("追踪标的")

    market_filter, type_filter, status_filter = _render_filters()

    @st.cache_data(ttl=30)
    def _fetch_assets(_market: str, _type: str, _status: bool | None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page_size": 100}
        if _market:
            params["market"] = _market
        if _type:
            params["asset_type"] = _type
        if _status is not None:
            params["enabled"] = _status
        result: dict[str, Any] = get_assets(**params)
        return result.get("items", [])

    items: list[dict[str, Any]] = _fetch_assets(market_filter, type_filter, status_filter)

    _render_asset_table(items)

    st.divider()
    _render_add_form()
    _render_search()
