from typing import Any

import streamlit as st

from ui.api_client import get_assets, get_asset, get_intraday, get_shareholder, get_reserve, get_dividend

ACTION_COLORS: dict[str, str] = {
    "buy": "green",
    "sell": "red",
    "watch": "orange",
    "avoid": "gray",
}

ACTION_LABELS: dict[str, str] = {
    "buy": "买入",
    "sell": "卖出",
    "watch": "观望",
    "avoid": "回避",
}


def _format_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿{suffix}"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万{suffix}"
    return f"{value:.2f}{suffix}"


@st.cache_data(ttl=30)
def _get_assets_cached() -> list[dict[str, Any]]:
    """获取追踪标的列表（缓存 30s）。

    必须在模块作用域：嵌套 def 会随每次 rerun 创建新函数对象，
    导致 st.cache_data 用函数身份做 key 时无法命中/无法 clear。
    """
    assets_result: dict[str, Any] = get_assets(page_size=100)
    return assets_result.get("items", [])


@st.cache_data(ttl=30)
def _get_detail_cached(_aid: int) -> dict[str, Any]:
    """获取标的详情（6 表 JOIN 结果，缓存 30s）。

    详情查询 ~50-200ms，缓存避免每次切 tab 都重拉。
    """
    return get_asset(_aid)


@st.cache_data(ttl=300)
def _fetch_intraday(_sym: str) -> dict[str, Any]:
    """获取分时走势数据（缓存 5min）。"""
    return get_intraday(_sym)


@st.cache_data(ttl=300)
def _fetch_shareholder(_sym: str) -> dict[str, Any]:
    """获取股东结构数据（缓存 5min）。"""
    return get_shareholder(_sym)


@st.cache_data(ttl=300)
def _fetch_reserve(_sym: str) -> dict[str, Any]:
    """获取业绩预告数据（缓存 5min）。"""
    return get_reserve(_sym)


@st.cache_data(ttl=300)
def _fetch_dividend(_sym: str) -> dict[str, Any]:
    """获取分红记录数据（缓存 5min）。"""
    return get_dividend(_sym)


def _render_quote_section(quote: dict[str, Any]) -> None:
    st.subheader("📈 行情")
    price: float | None = quote.get("price")
    change: float | None = quote.get("change")
    change_pct: float | None = quote.get("change_pct")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("最新价", f"{price:.2f}" if price is not None else "-")
    with m2:
        delta: str = f"{change:+.2f}" if change is not None else "-"
        st.metric("涨跌额", delta)
    with m3:
        if change_pct is not None:
            color: str = "normal" if change_pct >= 0 else "inverse"
            st.metric("涨跌幅", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
        else:
            st.metric("涨跌幅", "-")
    with m4:
        vol: float | None = quote.get("volume")
        st.metric("成交量", _format_number(vol))

    m5, m6, m7, m8 = st.columns(4)
    with m5:
        st.metric("开盘价", f"{quote.get('open', '-')}" if quote.get("open") is not None else "-")
    with m6:
        st.metric("最高价", f"{quote.get('high', '-')}" if quote.get("high") is not None else "-")
    with m7:
        st.metric("最低价", f"{quote.get('low', '-')}" if quote.get("low") is not None else "-")
    with m8:
        st.metric("昨收价", f"{quote.get('prev_close', '-')}" if quote.get("prev_close") is not None else "-")


def _render_kline_section(kline_summary: dict[str, Any]) -> None:
    st.subheader("📊 K 线摘要")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("最新收盘", f"{kline_summary.get('latest_close', '-')}" if kline_summary.get("latest_close") is not None else "-")
    with m2:
        st.metric("MA5", f"{kline_summary.get('ma5', '-')}" if kline_summary.get("ma5") is not None else "-")
    with m3:
        st.metric("MA20", f"{kline_summary.get('ma20', '-')}" if kline_summary.get("ma20") is not None else "-")
    with m4:
        st.metric("MA60", f"{kline_summary.get('ma60', '-')}" if kline_summary.get("ma60") is not None else "-")
    with m5:
        st.metric("趋势", kline_summary.get("trend", "-"))


def _render_finance_section(finance_summary: dict[str, Any]) -> None:
    st.subheader("💰 财务摘要")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("报告期", finance_summary.get("report_period", "-"))
    with m2:
        rev_yoy: float | None = finance_summary.get("revenue_yoy")
        st.metric("营收同比", f"{rev_yoy:+.1f}%" if rev_yoy is not None else "-")
    with m3:
        eps: float | None = finance_summary.get("eps")
        st.metric("EPS", f"{eps:.2f}" if eps is not None else "-")
    with m4:
        roe: float | None = finance_summary.get("roe")
        st.metric("ROE", f"{roe:.1f}%" if roe is not None else "-")


def _render_fund_flow_section(fund_flow_summary: dict[str, Any]) -> None:
    st.subheader("💹 资金流向")
    m1, m2 = st.columns(2)
    with m1:
        net_flow: float | None = fund_flow_summary.get("net_flow_5d")
        st.metric("近5日主力净流入", _format_number(net_flow))
    with m2:
        st.metric("趋势", fund_flow_summary.get("trend", "-"))


def _render_report_section(latest_report: dict[str, Any]) -> None:
    st.subheader("🧠 最新 AI 报告")
    action: str = latest_report.get("action", "")
    confidence: float | None = latest_report.get("confidence")
    risk_level: str = latest_report.get("risk_level", "")
    summary: str = latest_report.get("summary", "")

    c1, c2, c3 = st.columns(3)
    with c1:
        color: str = ACTION_COLORS.get(action, "gray")
        label: str = ACTION_LABELS.get(action, action)
        st.markdown(f"**动作建议:** :{color}[{label}]")
    with c2:
        if confidence is not None:
            st.progress(min(confidence, 1.0))
            st.caption(f"置信度: {confidence:.0%}")
        else:
            st.text("置信度: -")
    with c3:
        risk_labels: dict[str, str] = {"low": "低", "medium": "中", "high": "高"}
        st.markdown(f"**风险等级:** {risk_labels.get(risk_level, risk_level)}")

    st.markdown(f"> {summary}")

    bullish: list[str] = latest_report.get("bullish_reasons", [])
    bearish: list[str] = latest_report.get("bearish_reasons", [])
    if bullish:
        st.markdown("**看多理由:**")
        for reason in bullish:
            st.markdown(f"- :green[{reason}]")
    if bearish:
        st.markdown("**看空理由:**")
        for reason in bearish:
            st.markdown(f"- :red[{reason}]")

    key_risks: list[str] = latest_report.get("key_risks", [])
    if key_risks:
        st.markdown("**关键风险:**")
        for risk in key_risks:
            st.markdown(f"- ⚠️ {risk}")

    data_used: list[dict[str, Any]] = latest_report.get("data_used", [])
    if data_used:
        with st.expander("数据溯源"):
            for du in data_used:
                st.markdown(f"- `{du.get('source', '')}` / {du.get('type', '')} — {du.get('collected_at', '')}")


def render() -> None:
    st.header("标的详情")

    # 刷新数据按钮 — 清除本页所有 st.cache_data，强制重新拉取 API
    _hdr_col, _btn_col = st.columns([6, 1])
    with _btn_col:
        if st.button("刷新数据", use_container_width=True, help="清除缓存并重新拉取所有数据"):
            st.cache_data.clear()
            st.rerun()

    asset_items: list[dict[str, Any]] = _get_assets_cached()

    if not asset_items:
        st.info("暂无追踪标的，请先在「追踪标的」页面添加")
        return

    options: list[str] = [
        f"{a.get('symbol', '')} - {a.get('name', '')}" for a in asset_items
    ]
    asset_map: dict[str, dict[str, Any]] = {
        f"{a.get('symbol', '')} - {a.get('name', '')}": a for a in asset_items
    }

    selected: str | None = st.selectbox("选择标的", options, index=None, placeholder="请选择标的...")

    if selected is None:
        st.caption("请在上方选择一个标的查看详情")
        return

    asset: dict[str, Any] = asset_map[selected]
    asset_id: int = asset["id"]
    symbol: str = asset.get("symbol", "")

    st.markdown(f"### {symbol} — {asset.get('name', '')}")
    st.caption(
        f"市场: {asset.get('market', '').upper()} | "
        f"类型: {asset.get('asset_type', '')} | "
        f"状态: {'启用' if asset.get('enabled', True) else '停用'}"
    )

    # 详情查询（含 K线/财务/资金流向等 6 表 JOIN）单次 ~50-200ms，
    # 用 @st.cache_data(ttl=30) 复用结果，避免每次切 tab 都重拉。
    detail: dict[str, Any] = _get_detail_cached(asset_id)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "行情", "K 线", "财务", "资金流向", "分时走势", "股东结构", "业绩预告", "分红记录", "AI 报告",
    ])

    with tab1:
        quote: dict[str, Any] | None = detail.get("quote")
        if quote:
            _render_quote_section(quote)
        else:
            st.info("暂无行情数据")

    with tab2:
        kline_summary: dict[str, Any] | None = detail.get("kline_summary")
        if kline_summary:
            _render_kline_section(kline_summary)
        else:
            st.info("暂无 K 线数据")

    with tab3:
        finance_summary: dict[str, Any] | None = detail.get("finance_summary")
        if finance_summary:
            _render_finance_section(finance_summary)
        else:
            st.info("暂无财务数据")

    with tab4:
        fund_flow_summary: dict[str, Any] | None = detail.get("fund_flow_summary")
        if fund_flow_summary:
            _render_fund_flow_section(fund_flow_summary)
        else:
            st.info("暂无资金流向数据")

    with tab5:
        _render_intraday_tab(symbol)

    with tab6:
        _render_shareholder_tab(symbol)

    with tab7:
        _render_reserve_tab(symbol)

    with tab8:
        _render_dividend_tab(symbol)

    with tab9:
        latest_report: dict[str, Any] | None = detail.get("latest_report")
        if latest_report:
            _render_report_section(latest_report)
        else:
            st.info("暂无 AI 报告")


def _render_intraday_tab(symbol: str) -> None:
    st.subheader("分时走势")
    try:
        with st.spinner("正在采集分时数据（首次需调用 westock CLI）..."):
            result: dict[str, Any] = _fetch_intraday(symbol)
        items: list[dict[str, Any]] = result.get("items", [])
        if not items:
            st.info("暂无分时数据")
            return
        for row in items[:20]:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                time_str: str = str(row.get("time", "-"))
                st.text(time_str[-8:] if len(time_str) >= 8 else time_str)
            with c2:
                st.text(str(row.get("price", "-")))
            with c3:
                vol_val: Any = row.get("volume")
                if isinstance(vol_val, (int, float)):
                    st.text(f"{vol_val:,.0f}")
                else:
                    st.text(str(vol_val) if vol_val is not None else "-")
            with c4:
                st.text(str(row.get("avg_price", "-")))
        if len(items) > 20:
            st.caption(f"... 共 {len(items)} 条数据，仅显示前 20 条")
    except Exception as e:
        st.warning(f"分时数据加载失败: {e}")


def _render_shareholder_tab(symbol: str) -> None:
    st.subheader("股东结构")
    try:
        with st.spinner("正在采集股东结构..."):
            result: dict[str, Any] = _fetch_shareholder(symbol)
        top_shareholders: list[dict[str, Any]] = result.get("top_shareholders", [])
        if top_shareholders:
            st.markdown("**十大股东**")
            for h in top_shareholders:
                sc1, sc2, sc3 = st.columns([2, 2, 2])
                with sc1:
                    st.text(h.get("name", "-"))
                with sc2:
                    st.text(f"{h.get('shares', '-')} 股")
                with sc3:
                    pct: float | None = h.get("ratio")
                    st.text(f"{pct:.2f}%" if pct is not None else "-")
            st.divider()
        holder_count: list[dict[str, Any]] = result.get("holder_count_history", [])
        if holder_count:
            st.markdown("**股东人数变化**")
            for hc in holder_count[:10]:
                hc1, hc2 = st.columns(2)
                with hc1:
                    st.text(str(hc.get("date", "-")))
                with hc2:
                    st.text(str(hc.get("total_holders", "-")))
        if not top_shareholders and not holder_count:
            st.info("暂无股东结构数据")
    except Exception as e:
        st.warning(f"股东数据加载失败: {e}")


def _render_reserve_tab(symbol: str) -> None:
    st.subheader("业绩预告")
    try:
        with st.spinner("正在采集业绩预告..."):
            result: dict[str, Any] = _fetch_reserve(symbol)
        forecast_type: str = result.get("forecast_type", "") or result.get("report_period", "")
        if not forecast_type and not result.get("profit_lower"):
            st.info("暂无业绩预告数据")
            return
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("预告类型", forecast_type or "-")
        with rc2:
            profit_lower: float | None = result.get("profit_lower")
            st.metric("利润下限", f"{profit_lower / 1e8:.2f}亿" if profit_lower else "-")
        with rc3:
            profit_upper: float | None = result.get("profit_upper")
            st.metric("利润上限", f"{profit_upper / 1e8:.2f}亿" if profit_upper else "-")
        summary: str = result.get("summary", "")
        if summary:
            st.markdown(f"> {summary}")
    except Exception as e:
        st.warning(f"业绩预告加载失败: {e}")


def _render_dividend_tab(symbol: str) -> None:
    st.subheader("分红记录")
    try:
        with st.spinner("正在采集分红记录..."):
            result: dict[str, Any] = _fetch_dividend(symbol)
        items: list[dict[str, Any]] = result.get("items", [])
        if not items:
            st.info("暂无分红记录")
            return
        for d in items:
            dc1, dc2, dc3, dc4 = st.columns(4)
            with dc1:
                st.text(f"除权日: {d.get('ex_date', '-')}")
            with dc2:
                st.text(f"每股分红: {d.get('cash_dividend', '-')}")
            with dc3:
                st.text(f"送股: {d.get('share_bonus', '-')}")
            with dc4:
                st.text(f"登记日: {d.get('record_date', '-')}")
            st.divider()
    except Exception as e:
        st.warning(f"分红数据加载失败: {e}")