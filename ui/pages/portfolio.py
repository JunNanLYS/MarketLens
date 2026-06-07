import time
from collections.abc import Callable
from typing import Any

import streamlit as st

from ui.api_client import (
    get_accounts,
    create_account,
    update_account,
    delete_account,
    get_transactions,
    create_transaction,
    update_transaction,
    delete_transaction,
    get_positions,
    get_realized_pnl,
)

TRANSACTION_TYPE_LABELS: dict[str, str] = {
    "buy": "买入",
    "sell": "卖出",
    "dividend": "分红",
    "split": "拆股",
}

CURRENCY_OPTIONS: list[str] = ["CNY", "HKD", "USD"]


# ---------------------------------------------------------------------------
# 第 5 轮改造（review-r5）：session_state 字典版 cache + 细粒度失效
# ---------------------------------------------------------------------------
# 旧实现用 `@st.cache_data` + `st.cache_data.clear()` 全局清，副作用是编辑
# 单笔交易后清空详情页/新闻/板块 等所有页面的 cache → 冷启动 ~50-200ms。
# 改造为页面级 session_state 字典：每个写操作只清本页面相关 prefix。
# 跨页面隔离：portfolio 写操作不再影响 asset_detail / news_list 缓存。
# ---------------------------------------------------------------------------

_CACHE_KEY: str = "_portfolio_cache"


def _init_cache() -> None:
    """初始化页面级 session_state cache 字典。

    模块作用域调用，rerun 期间幂等。
    """
    if _CACHE_KEY not in st.session_state:
        st.session_state[_CACHE_KEY] = {}


def _cached_get(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    """按 key 读取/写入 cache；TTL 到期或缺失时调用 fn() 重建。

    session_state 字典版 cache：单用户本地工具，key 数量有限（5-10 个账户）
    无需 LRU 淘汰；TTL 自然过期。
    """
    cache: dict[str, dict[str, Any]] = st.session_state[_CACHE_KEY]
    now: float = time.time()
    entry: dict[str, Any] | None = cache.get(key)
    if entry is not None and now - entry["ts"] < ttl:
        return entry["value"]
    value: Any = fn()
    cache[key] = {"ts": now, "value": value}
    return value


def _invalidate_cache(prefix: str) -> None:
    """按前缀清空 cache；空字符串 = 清空本页面全部 cache。

    细粒度失效：写交易/账户只清本页面相关 key，不影响其他页面。
    """
    if prefix == "":
        st.session_state[_CACHE_KEY] = {}
    else:
        cache: dict[str, dict[str, Any]] = st.session_state[_CACHE_KEY]
        st.session_state[_CACHE_KEY] = {
            k: v for k, v in cache.items() if not k.startswith(prefix)
        }


_init_cache()


def _fetch_accounts_raw() -> list[dict[str, Any]]:
    """拉取账户列表（无缓存纯函数，供 _cached_get 包装）。"""
    return get_accounts()


def _fetch_accounts() -> list[dict[str, Any]]:
    """缓存账户列表（TTL 15s，session_state 字典版）。

    portfolio 页面 3 处需要 get_accounts()（positions / transactions / accounts tab），
    每次都重拉会阻塞 Streamlit。session_state 字典版支持细粒度失效：
    写操作后调用 _invalidate_cache("accounts") 只清本页面，不影响其他页面。
    """
    return _cached_get("accounts", 15, _fetch_accounts_raw)


def _format_pnl(value: float | None) -> str:
    if value is None:
        return "-"
    sign: str = "+" if value > 0 else ""
    return f"{sign}{value:,.2f}"


def _pnl_arrow(value: float) -> str:
    """根据盈亏正负返回 ▲/▼ 文本前缀，供颜色盲用户识别涨跌方向。

    0 不加前缀（不涨不跌无方向信号）；正负值分别用 ▲ / ▼ 配合后续的
    :green[...] / :red[...] 颜色，文本符号作为主信号、颜色作为辅助信号，
    满足 ~8% 男性红绿色盲可达性要求（CLAUDE.md / ISSUES.md）。
    """
    if value > 0:
        return "▲"
    if value < 0:
        return "▼"
    return ""


def _render_positions_tab() -> None:
    positions: list[dict[str, Any]] = get_positions()

    if not positions:
        st.info("暂无持仓")
        return

    account_map: dict[int, str] = {a["id"]: a.get("name", "") for a in _fetch_accounts()}

    total_market_value: float = 0.0
    total_unrealized_pnl: float = 0.0

    for pos in positions:
        mv: float = pos.get("market_value", 0.0) or 0.0
        upnl: float = pos.get("unrealized_pnl", 0.0) or 0.0
        total_market_value += mv
        total_unrealized_pnl += upnl

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("总市值", f"{total_market_value:,.2f}")
    with m2:
        st.metric("总浮动盈亏", _format_pnl(total_unrealized_pnl))
    with m3:
        if total_market_value > 0:
            pct: float = total_unrealized_pnl / (total_market_value - total_unrealized_pnl) * 100
            st.metric("总浮动盈亏率", f"{pct:+.2f}%")
        else:
            st.metric("总浮动盈亏率", "-")

    st.divider()

    for pos in positions:
        cols = st.columns([2, 2, 1.5, 1.5, 2, 2, 2])
        with cols[0]:
            st.markdown(f"**{pos.get('symbol', '')}**")
            st.caption(pos.get("name", ""))
        with cols[1]:
            account_id: int | None = pos.get("account_id")
            if account_id is not None and account_id in account_map:
                st.text(f"账户 {account_map[account_id]}")
            else:
                st.text("-")
        with cols[2]:
            qty: float | None = pos.get("total_qty")
            st.text(f"{qty:.0f}" if qty is not None else "-")
        with cols[3]:
            avg: float | None = pos.get("avg_cost")
            st.text(f"{avg:.2f}" if avg is not None else "-")
        with cols[4]:
            mv_val: float | None = pos.get("market_value")
            st.text(f"{mv_val:,.2f}" if mv_val is not None else "-")
        with cols[5]:
            upnl_val: float | None = pos.get("unrealized_pnl")
            if upnl_val is not None:
                pnl_color: str = "green" if upnl_val > 0 else "red" if upnl_val < 0 else "inherit"
                arrow: str = _pnl_arrow(upnl_val)
                pnl_str: str = _format_pnl(upnl_val)
                st.markdown(f":{pnl_color}[{arrow} {pnl_str}]".strip())
            else:
                st.text("-")
        with cols[6]:
            upnl_pct: float | None = pos.get("unrealized_pnl_pct")
            if upnl_pct is not None:
                pct_color: str = "green" if upnl_pct > 0 else "red" if upnl_pct < 0 else "inherit"
                pct_arrow: str = _pnl_arrow(upnl_pct)
                st.markdown(f":{pct_color}[{pct_arrow} {upnl_pct:+.2f}%]".strip())
            else:
                st.text("-")

    st.divider()
    st.subheader("已实现盈亏")
    realized_resp: dict[str, Any] = get_realized_pnl()
    realized: list[dict[str, Any]] = realized_resp.get("items", [])
    if not realized:
        st.info("暂无已实现盈亏记录")
    else:
        total_realized: float = 0.0
        for rp in realized:
            pnl: float = rp.get("realized_pnl", 0.0) or 0.0
            total_realized += pnl
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1:
                st.text(rp.get("symbol", ""))
            with rc2:
                st.text(f"账户 {rp.get('account_id', '')}")
            with rc3:
                st.text(f"卖出数量: {rp.get('total_sell_qty', 0):.0f}")
            with rc4:
                rp_color: str = "green" if pnl > 0 else "red" if pnl < 0 else "inherit"
                rp_arrow: str = _pnl_arrow(pnl)
                st.markdown(f":{rp_color}[{rp_arrow} {_format_pnl(pnl)}]".strip())
        st.divider()
        tr_color: str = "green" if total_realized > 0 else "red" if total_realized < 0 else "inherit"
        tr_arrow: str = _pnl_arrow(total_realized)
        st.markdown(f"**总已实现盈亏:** :{tr_color}[{tr_arrow} {_format_pnl(total_realized)}]".strip())


def _render_transactions_tab() -> None:
    accounts: list[dict[str, Any]] = _fetch_accounts()
    account_options: dict[str, int | None] = {"全部": None}
    for acc in accounts:
        account_options[f"{acc.get('name', '')} (ID: {acc.get('id', '')})"] = acc.get("id")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_account: str = st.selectbox("账户", list(account_options.keys()), key="tx_filter_account")
    with col2:
        tx_type: str = st.selectbox(
            "交易类型",
            ["全部", "buy", "sell", "dividend", "split"],
            key="tx_filter_type",
        )
    with col3:
        symbol_filter: str = st.text_input("标的代码", key="tx_filter_symbol")

    params: dict[str, Any] = {"page_size": 50}
    account_id: int | None = account_options[selected_account]
    if account_id is not None:
        params["account_id"] = account_id
    if tx_type != "全部":
        params["type"] = tx_type
    if symbol_filter.strip():
        params["symbol"] = symbol_filter.strip()

    result: dict[str, Any] = get_transactions(**params)
    items: list[dict[str, Any]] = result.get("items", [])

    if not items:
        st.info("暂无交易记录")
    else:
        for tx_idx, tx in enumerate(items):
            with st.container():
                # 优先用 id 作 key；id 缺失时回退到索引，避免 Streamlit DuplicateWidgetID 错误
                tx_key = tx.get("id") if tx.get("id") is not None else f"idx_{tx_idx}"
                tc1, tc2, tc3, tc4, tc5, tc6 = st.columns([2, 1, 1.5, 1.5, 1.5, 1])
                with tc1:
                    st.markdown(f"**{tx.get('symbol', '')}**")
                with tc2:
                    tx_type_val: str = tx.get("type", "")
                    type_label: str = TRANSACTION_TYPE_LABELS.get(tx_type_val, tx_type_val)
                    type_color: str = "green" if tx_type_val == "buy" else "red" if tx_type_val == "sell" else "orange"
                    st.markdown(f":{type_color}[{type_label}]")
                with tc3:
                    qty_val: float | None = tx.get("quantity")
                    st.text(f"数量: {qty_val}" if qty_val is not None else "-")
                with tc4:
                    price_val: float | None = tx.get("price")
                    st.text(f"价格: {price_val}" if price_val is not None else "-")
                with tc5:
                    st.text(f"日期: {tx.get('trade_date', '-')}")
                with tc6:
                    if st.button("✏️", key=f"edit_tx_{tx_key}", help="编辑该交易"):
                        st.session_state[f"edit_tx_{tx_key}"] = True
                        st.rerun()
                    if st.button("🗑️", key=f"del_tx_{tx_key}", help="删除该交易"):
                        st.session_state[f"confirm_del_tx_{tx_key}"] = True
                        st.rerun()

                if st.session_state.get(f"edit_tx_{tx_key}"):
                    with st.form(f"edit_transaction_form_{tx_key}"):
                        st.markdown(f"**编辑交易 #{tx.get('id', '')} — {tx.get('symbol', '')}**")
                        ex1, ex2, ex3 = st.columns(3)
                        with ex1:
                            new_qty: float = st.number_input("数量 *", min_value=0.01, value=float(tx.get("quantity", 0) or 0), step=1.0, key=f"etx_qty_{tx_key}")
                        with ex2:
                            new_price: float = st.number_input("价格 *", min_value=0.01, value=float(tx.get("price", 0) or 0), step=0.01, key=f"etx_price_{tx_key}")
                        with ex3:
                            new_fee: float = st.number_input("手续费", min_value=0.0, value=float(tx.get("fee", 0) or 0), step=0.01, key=f"etx_fee_{tx_key}")
                        new_notes: str = st.text_input("备注", value=tx.get("notes", "") or "", key=f"etx_notes_{tx_key}")
                        es1, es2 = st.columns(2)
                        with es1:
                            if st.form_submit_button("保存"):
                                upd: dict[str, Any] = {"quantity": new_qty, "price": new_price, "fee": new_fee}
                                if new_notes.strip():
                                    upd["notes"] = new_notes.strip()
                                result_upd_tx: dict[str, Any] = update_transaction(int(tx["id"]), upd)
                                if "error" in result_upd_tx or "id" not in result_upd_tx:
                                    st.error(result_upd_tx.get("detail", "更新失败"))
                                    return
                                # 细粒度失效：编辑单笔交易只清本页面 accounts cache，
                                # 不影响详情页 / 新闻 / 板块等其他页面的 cache。
                                _invalidate_cache("accounts")
                                st.session_state.pop(f"edit_tx_{tx_key}", None)
                                st.success("已更新")
                                st.rerun()
                        with es2:
                            if st.form_submit_button("取消"):
                                st.session_state.pop(f"edit_tx_{tx_key}", None)
                                st.rerun()

                if st.session_state.get(f"confirm_del_tx_{tx_key}"):
                    st.warning(f"确认删除交易 {tx.get('id', '')}？")
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("确认", key=f"confirm_del_tx_btn_{tx_key}"):
                            result_del_tx: dict[str, Any] = delete_transaction(tx["id"])
                            if "error" in result_del_tx or "id" not in result_del_tx:
                                st.error(result_del_tx.get("detail", "删除失败"))
                                return
                            # 细粒度失效：删除单笔交易只清本页面 accounts cache。
                            _invalidate_cache("accounts")
                            st.session_state.pop(f"confirm_del_tx_{tx_key}", None)
                            st.success("已删除")
                            st.rerun()
                    with bc2:
                        if st.button("取消", key=f"cancel_del_tx_btn_{tx_key}"):
                            st.session_state.pop(f"confirm_del_tx_{tx_key}", None)
                            st.rerun()

    st.divider()
    st.subheader("录入交易")
    with st.form("add_transaction_form"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            tx_accounts: list[dict[str, Any]] = _fetch_accounts()
            tx_account_options: dict[str, int] = {
                f"{a.get('name', '')} (ID: {a.get('id', '')})": a["id"]
                for a in tx_accounts
            }
            selected_tx_account: str = st.selectbox(
                "账户 *",
                list(tx_account_options.keys()) if tx_account_options else ["无可用账户"],
                key="tx_account",
            )
        with fc2:
            tx_symbol: str = st.text_input("标的代码 *", key="tx_symbol")
        with fc3:
            tx_type_select: str = st.selectbox(
                "交易类型 *",
                ["buy", "sell", "dividend", "split"],
                format_func=lambda x: TRANSACTION_TYPE_LABELS.get(x, x),
                key="tx_type_select",
            )

        fc4, fc5, fc6, fc7 = st.columns(4)
        with fc4:
            tx_quantity: float = st.number_input("数量 *", min_value=0.01, value=100.0, step=1.0, key="tx_quantity")
        with fc5:
            tx_price: float = st.number_input("价格 *", min_value=0.01, value=1.0, step=0.01, key="tx_price")
        with fc6:
            tx_fee: float = st.number_input("手续费", min_value=0.0, value=0.0, step=0.01, key="tx_fee")
        with fc7:
            tx_date: str = st.date_input("交易日期 *", key="tx_date").isoformat()

        tx_notes: str = st.text_input("备注", key="tx_notes")

        submitted: bool = st.form_submit_button("录入")
        if submitted:
            if not tx_symbol.strip():
                st.error("请输入标的代码")
            elif not tx_account_options:
                st.error("请先创建账户")
            else:
                data: dict[str, Any] = {
                    "account_id": tx_account_options[selected_tx_account],
                    "symbol": tx_symbol.strip(),
                    "type": tx_type_select,
                    "quantity": tx_quantity,
                    "price": tx_price,
                    "fee": tx_fee,
                    "trade_date": tx_date,
                }
                if tx_notes.strip():
                    data["notes"] = tx_notes.strip()
                result_tx: dict[str, Any] = create_transaction(data)
                if "error" in result_tx or "id" not in result_tx:
                    st.error(result_tx.get("detail", "交易录入失败"))
                    return
                # 细粒度失效：录入交易只清本页面 accounts cache。
                _invalidate_cache("accounts")
                st.success("交易录入成功")
                st.rerun()


def _render_accounts_tab() -> None:
    st.subheader("账户列表")
    accounts: list[dict[str, Any]] = _fetch_accounts()

    if accounts:
        for acc in accounts:
            with st.container():
                ac1, ac2, ac3, ac4, ac5 = st.columns([2, 2, 1, 2, 1])
                with ac1:
                    st.markdown(f"**{acc.get('name', '')}**")
                with ac2:
                    st.text(acc.get("broker", "-") or "-")
                with ac3:
                    st.text(acc.get("currency", "CNY"))
                with ac4:
                    st.text(acc.get("notes", "") or "")
                with ac5:
                    acc_id: int = acc.get("id", 0)
                    if st.button("✏️", key=f"edit_acc_{acc_id}", help="编辑该账户"):
                        st.session_state[f"edit_acc_{acc_id}"] = True
                        st.rerun()
                    if st.button("🗑️", key=f"del_acc_{acc_id}", help="删除该账户"):
                        st.session_state[f"confirm_del_acc_{acc_id}"] = True
                        st.rerun()

                if st.session_state.get(f"edit_acc_{acc_id}"):
                    with st.form(f"edit_account_form_{acc_id}"):
                        st.markdown(f"**编辑账户「{acc.get('name', '')}」**")
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        with ec1:
                            new_name: str = st.text_input("名称 *", value=acc.get("name", ""), key=f"eacc_name_{acc_id}")
                        with ec2:
                            new_broker: str = st.text_input("券商", value=acc.get("broker", "") or "", key=f"eacc_broker_{acc_id}")
                        with ec3:
                            new_currency: str = st.selectbox("币种", CURRENCY_OPTIONS, index=CURRENCY_OPTIONS.index(acc.get("currency", "CNY")) if acc.get("currency") in CURRENCY_OPTIONS else 0, key=f"eacc_currency_{acc_id}")
                        with ec4:
                            new_notes: str = st.text_input("备注", value=acc.get("notes", "") or "", key=f"eacc_notes_{acc_id}")
                        es1, es2 = st.columns(2)
                        with es1:
                            if st.form_submit_button("保存"):
                                if not new_name.strip():
                                    st.error("请输入账户名称")
                                else:
                                    upd: dict[str, Any] = {"name": new_name.strip(), "currency": new_currency}
                                    if new_broker.strip():
                                        upd["broker"] = new_broker.strip()
                                    if new_notes.strip():
                                        upd["notes"] = new_notes.strip()
                                    result_upd_acc: dict[str, Any] = update_account(acc_id, upd)
                                    if "error" in result_upd_acc or "id" not in result_upd_acc:
                                        st.error(result_upd_acc.get("detail", "更新失败"))
                                        return
                                    # 细粒度失效：编辑账户只清本页面 accounts cache。
                                    _invalidate_cache("accounts")
                                    st.session_state.pop(f"edit_acc_{acc_id}", None)
                                    st.success("已更新")
                                    st.rerun()
                        with es2:
                            if st.form_submit_button("取消"):
                                st.session_state.pop(f"edit_acc_{acc_id}", None)
                                st.rerun()

                if st.session_state.get(f"confirm_del_acc_{acc_id}"):
                    st.warning(f"确认删除账户「{acc.get('name', '')}」？关联交易记录将保留。")
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        if st.button("确认", key=f"confirm_del_acc_btn_{acc_id}"):
                            result_del_acc: dict[str, Any] = delete_account(acc_id)
                            if "error" in result_del_acc or "id" not in result_del_acc:
                                st.error(result_del_acc.get("detail", "删除失败"))
                                return
                            # 细粒度失效：删除账户只清本页面 accounts cache。
                            _invalidate_cache("accounts")
                            st.session_state.pop(f"confirm_del_acc_{acc_id}", None)
                            st.success("已删除")
                            st.rerun()
                    with dc2:
                        if st.button("取消", key=f"cancel_del_acc_btn_{acc_id}"):
                            st.session_state.pop(f"confirm_del_acc_{acc_id}", None)
                            st.rerun()
    else:
        st.info("暂无账户")

    st.divider()
    st.subheader("创建账户")
    with st.form("create_account_form"):
        nc1, nc2, nc3, nc4 = st.columns(4)
        with nc1:
            acc_name: str = st.text_input("账户名称 *", key="acc_name")
        with nc2:
            acc_broker: str = st.text_input("券商", key="acc_broker")
        with nc3:
            acc_currency: str = st.selectbox("币种", CURRENCY_OPTIONS, key="acc_currency")
        with nc4:
            acc_notes: str = st.text_input("备注", key="acc_notes")

        submitted: bool = st.form_submit_button("创建")
        if submitted:
            if not acc_name.strip():
                st.error("请输入账户名称")
            else:
                data: dict[str, Any] = {
                    "name": acc_name.strip(),
                    "currency": acc_currency,
                }
                if acc_broker.strip():
                    data["broker"] = acc_broker.strip()
                if acc_notes.strip():
                    data["notes"] = acc_notes.strip()
                result_acc: dict[str, Any] = create_account(data)
                if "error" in result_acc or "id" not in result_acc:
                    st.error(result_acc.get("detail", "账户创建失败"))
                    return
                # 细粒度失效：创建账户只清本页面 accounts cache。
                _invalidate_cache("accounts")
                st.success(f"账户「{acc_name.strip()}」创建成功")
                st.rerun()


def render() -> None:
    st.header("投资组合")

    tab_positions, tab_transactions, tab_accounts = st.tabs(
        ["持仓总览", "交易记录", "账户管理"]
    )

    with tab_positions:
        _render_positions_tab()

    with tab_transactions:
        _render_transactions_tab()

    with tab_accounts:
        _render_accounts_tab()
