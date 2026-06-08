import time
from collections.abc import Callable
from typing import Any

import streamlit as st

from ui.api_client import (
    get_assets,
    get_asset,
    get_intraday,
    get_shareholder,
    get_reserve,
    get_dividend,
    get_etf_info,
    get_etf_holdings,
    get_etf_nav,
    get_sectors_board,
    get_sectors_hot,
    get_ipo_calendar,
    get_exdiv_calendar,
    get_chip,
)

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


# ---------------------------------------------------------------------------
# 第 5 轮改造（review-r5）：session_state 字典版 cache + 细粒度失效
# ---------------------------------------------------------------------------
# 旧实现用 `@st.cache_data` 装饰 + `st.cache_data.clear()` 全局清，副作用是
# 详情页刷新按钮会清空所有页面（portfolio / news / settings）的 cache。
# 改造为页面级 session_state 字典：刷新按钮只清本页面 14 个 key。
# 跨页面隔离：详情页刷新不再影响其他页面缓存。
# ---------------------------------------------------------------------------

_CACHE_KEY: str = "_asset_detail_cache"


def _init_cache() -> None:
    """初始化页面级 session_state cache 字典。模块作用域，rerun 幂等。"""
    if _CACHE_KEY not in st.session_state:
        st.session_state[_CACHE_KEY] = {}


def _cached_get(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    """按 key 读取/写入 cache；TTL 到期或缺失时调用 fn() 重建。"""
    cache: dict[str, dict[str, Any]] = st.session_state[_CACHE_KEY]
    now: float = time.time()
    entry: dict[str, Any] | None = cache.get(key)
    if entry is not None and now - entry["ts"] < ttl:
        return entry["value"]
    value: Any = fn()
    cache[key] = {"ts": now, "value": value}
    return value


def _invalidate_cache(prefix: str) -> None:
    """按前缀清空 cache；空字符串 = 清空本页面全部 cache。"""
    if prefix == "":
        st.session_state[_CACHE_KEY] = {}
    else:
        cache: dict[str, dict[str, Any]] = st.session_state[_CACHE_KEY]
        st.session_state[_CACHE_KEY] = {
            k: v for k, v in cache.items() if not k.startswith(prefix)
        }


_init_cache()


def _get_assets_cached_raw() -> list[dict[str, Any]]:
    """获取追踪标的列表（无缓存纯函数）。"""
    assets_result: dict[str, Any] = get_assets(page_size=100)
    return assets_result.get("items", [])


def _get_assets_cached() -> list[dict[str, Any]]:
    """获取追踪标的列表（session_state 字典版，TTL 30s）。

    标的列表变更频次低（用户手动添加/删除/启用），30s TTL 够用。
    """
    return _cached_get("assets", 30, _get_assets_cached_raw)


def _get_detail_cached_raw(_aid: int) -> dict[str, Any]:
    """获取标的详情（6 表 JOIN 结果，无缓存纯函数）。"""
    return get_asset(_aid)


def _get_detail_cached(_aid: int) -> dict[str, Any]:
    """获取标的详情（session_state 字典版，TTL 30s）。

    详情查询 ~50-200ms，缓存避免每次切 tab 都重拉。
    """
    return _cached_get(f"detail:{_aid}", 30, lambda: _get_detail_cached_raw(_aid))


def _fetch_intraday_raw(_sym: str) -> dict[str, Any]:
    """获取分时走势数据（无缓存纯函数）。"""
    return get_intraday(_sym)


def _fetch_intraday(_sym: str) -> dict[str, Any]:
    """获取分时走势数据（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"intraday:{_sym}", 300, lambda: _fetch_intraday_raw(_sym))


def _fetch_shareholder_raw(_sym: str) -> dict[str, Any]:
    """获取股东结构数据（无缓存纯函数）。"""
    return get_shareholder(_sym)


def _fetch_shareholder(_sym: str) -> dict[str, Any]:
    """获取股东结构数据（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"shareholder:{_sym}", 300, lambda: _fetch_shareholder_raw(_sym))


def _fetch_reserve_raw(_sym: str) -> dict[str, Any]:
    """获取业绩预告数据（无缓存纯函数）。"""
    return get_reserve(_sym)


def _fetch_reserve(_sym: str) -> dict[str, Any]:
    """获取业绩预告数据（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"reserve:{_sym}", 300, lambda: _fetch_reserve_raw(_sym))


def _fetch_dividend_raw(_sym: str) -> dict[str, Any]:
    """获取分红记录数据（无缓存纯函数）。"""
    return get_dividend(_sym)


def _fetch_dividend(_sym: str) -> dict[str, Any]:
    """获取分红记录数据（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"dividend:{_sym}", 300, lambda: _fetch_dividend_raw(_sym))


def _fetch_etf_info_raw(_sym: str) -> dict[str, Any]:
    """获取 ETF 基本信息（无缓存纯函数）。"""
    return get_etf_info(_sym)


def _fetch_etf_info(_sym: str) -> dict[str, Any]:
    """获取 ETF 基本信息（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"etf_info:{_sym}", 300, lambda: _fetch_etf_info_raw(_sym))


def _fetch_etf_holdings_raw(_sym: str) -> dict[str, Any]:
    """获取 ETF 成分股（无缓存纯函数）。"""
    return get_etf_holdings(_sym, limit=50)


def _fetch_etf_holdings(_sym: str) -> dict[str, Any]:
    """获取 ETF 成分股（session_state 字典版，TTL 5min）。"""
    return _cached_get(
        f"etf_holdings:{_sym}", 300, lambda: _fetch_etf_holdings_raw(_sym)
    )


def _fetch_etf_nav_raw(_sym: str) -> dict[str, Any]:
    """获取 ETF 历史净值（无缓存纯函数）。"""
    return get_etf_nav(_sym, limit=60)


def _fetch_etf_nav(_sym: str) -> dict[str, Any]:
    """获取 ETF 历史净值（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"etf_nav:{_sym}", 300, lambda: _fetch_etf_nav_raw(_sym))


def _fetch_sectors_board_raw() -> dict[str, Any]:
    """获取板块首页（无缓存纯函数）。"""
    return get_sectors_board(limit=50)


def _fetch_sectors_board() -> dict[str, Any]:
    """获取板块首页（session_state 字典版，TTL 5min）。"""
    return _cached_get("sectors_board", 300, _fetch_sectors_board_raw)


def _fetch_sectors_hot_raw() -> dict[str, Any]:
    """获取热门板块（无缓存纯函数）。"""
    return get_sectors_hot(limit=10)


def _fetch_sectors_hot() -> dict[str, Any]:
    """获取热门板块（session_state 字典版，TTL 5min）。"""
    return _cached_get("sectors_hot", 300, _fetch_sectors_hot_raw)


def _fetch_ipo_calendar_raw(_market: str) -> dict[str, Any]:
    """获取 IPO 日历（无缓存纯函数）。"""
    return get_ipo_calendar(market=_market, limit=50)


def _fetch_ipo_calendar(_market: str) -> dict[str, Any]:
    """获取 IPO 日历（session_state 字典版，TTL 10min）。"""
    return _cached_get(
        f"ipo_calendar:{_market}", 600, lambda: _fetch_ipo_calendar_raw(_market)
    )


def _fetch_exdiv_calendar_raw(_sym: str) -> dict[str, Any]:
    """获取除权日历（无缓存纯函数）。"""
    return get_exdiv_calendar(_sym)


def _fetch_exdiv_calendar(_sym: str) -> dict[str, Any]:
    """获取除权日历（session_state 字典版，TTL 10min）。"""
    return _cached_get(
        f"exdiv_calendar:{_sym}", 600, lambda: _fetch_exdiv_calendar_raw(_sym)
    )


def _fetch_chip_raw(_sym: str) -> dict[str, Any]:
    """获取筹码分布（无缓存纯函数）。"""
    return get_chip(_sym, limit=20)


def _fetch_chip(_sym: str) -> dict[str, Any]:
    """获取筹码分布（session_state 字典版，TTL 5min）。"""
    return _cached_get(f"chip:{_sym}", 300, lambda: _fetch_chip_raw(_sym))


def _format_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿{suffix}"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万{suffix}"
    return f"{value:.2f}{suffix}"


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
            st.metric("涨跌幅", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
        else:
            st.metric("涨跌幅", "-")
    with m4:
        vol: float | None = quote.get("volume")
        st.metric("成交量", _format_number(vol))

    m5, m6, m7, m8 = st.columns(4)
    with m5:
        st.metric(
            "开盘价",
            f"{quote.get('open', '-')}" if quote.get("open") is not None else "-",
        )
    with m6:
        st.metric(
            "最高价",
            f"{quote.get('high', '-')}" if quote.get("high") is not None else "-",
        )
    with m7:
        st.metric(
            "最低价",
            f"{quote.get('low', '-')}" if quote.get("low") is not None else "-",
        )
    with m8:
        st.metric(
            "昨收价",
            f"{quote.get('prev_close', '-')}"
            if quote.get("prev_close") is not None
            else "-",
        )


def _render_kline_section(kline_summary: dict[str, Any]) -> None:
    st.subheader("📊 K 线摘要")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric(
            "最新收盘",
            f"{kline_summary.get('latest_close', '-')}"
            if kline_summary.get("latest_close") is not None
            else "-",
        )
    with m2:
        st.metric(
            "MA5",
            f"{kline_summary.get('ma5', '-')}"
            if kline_summary.get("ma5") is not None
            else "-",
        )
    with m3:
        st.metric(
            "MA20",
            f"{kline_summary.get('ma20', '-')}"
            if kline_summary.get("ma20") is not None
            else "-",
        )
    with m4:
        st.metric(
            "MA60",
            f"{kline_summary.get('ma60', '-')}"
            if kline_summary.get("ma60") is not None
            else "-",
        )
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
    key_risks: list[str] = latest_report.get("key_risks", [])
    if bullish:
        st.markdown("**看多理由:**")
        for reason in bullish:
            st.markdown(f"- :green[▲ {reason}]")
    # 关键风险与看空理由互斥：risk_level==high 时 key_risks 已是
    # bearish_reasons 的独立高危子集（见 ai_analyzer.py:140-147），
    # 同时显示会出现两份相似列表的视觉冗余。
    if key_risks:
        st.markdown("**关键风险:**")
        for risk in key_risks:
            st.markdown(f"- ⚠️ {risk}")
    elif bearish:
        st.markdown("**看空理由:**")
        for reason in bearish:
            st.markdown(f"- :red[▼ {reason}]")

    data_used: list[dict[str, Any]] = latest_report.get("data_used", [])
    if data_used:
        with st.expander("数据溯源"):
            for du in data_used:
                st.markdown(
                    f"- `{du.get('source', '')}` / {du.get('type', '')} — {du.get('collected_at', '')}"
                )


def render() -> None:
    st.header("标的详情")

    # 刷新数据按钮 — 清除本页所有 session_state cache，强制重新拉取 API。
    # 第 5 轮改造：空字符串 prefix 清空本页面 14 个 cache key，
    # 不再清空其他页面的 cache（之前 st.cache_data.clear() 是全局清）。
    _hdr_col, _btn_col = st.columns([6, 1])
    with _btn_col:
        if st.button(
            "刷新数据", use_container_width=True, help="清除本页缓存并重新拉取所有数据"
        ):
            _invalidate_cache("")
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

    selected: str | None = st.selectbox(
        "选择标的", options, index=None, placeholder="请选择标的..."
    )

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
    # 用 session_state 字典版 cache（TTL 30s）复用结果，避免每次切 tab 都重拉。
    detail: dict[str, Any] = _get_detail_cached(asset_id)

    # 动态构建 tab 列表：ETF tab 仅当 asset_type == "etf" 时显示，
    # 避免在非 ETF 标的页出现一个永远为空的 tab（更可发现、更可访问）。
    is_etf: bool = asset.get("asset_type", "") == "etf"
    tab_labels: list[str] = [
        "行情",
        "K 线",
        "财务",
        "资金流向",
        "分时走势",
        "股东结构",
        "业绩预告",
        "分红记录",
        "AI 报告",
    ]
    if is_etf:
        tab_labels.append("ETF")
    tab_labels.extend(["行业板块", "日历", "筹码/融资融券"])

    tabs: tuple[Any, ...] = st.tabs(tab_labels)
    (tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, *extra_tabs) = tabs

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

    # 追加 tab：ETF（条件渲染） / 行业板块 / 日历 / 筹码+融资融券
    if is_etf:
        with extra_tabs[0]:
            _render_etf_tab(symbol)
    with extra_tabs[1 if is_etf else 0]:
        _render_sectors_tab()
    with extra_tabs[2 if is_etf else 1]:
        _render_calendar_tab(symbol)
    with extra_tabs[3 if is_etf else 2]:
        _render_chip_tab(symbol)


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
        forecast_type: str = result.get("forecast_type", "") or result.get(
            "report_period", ""
        )
        if not forecast_type and not result.get("profit_lower"):
            st.info("暂无业绩预告数据")
            return
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("预告类型", forecast_type or "-")
        with rc2:
            profit_lower: float | None = result.get("profit_lower")
            st.metric(
                "利润下限", f"{profit_lower / 1e8:.2f}亿" if profit_lower else "-"
            )
        with rc3:
            profit_upper: float | None = result.get("profit_upper")
            st.metric(
                "利润上限", f"{profit_upper / 1e8:.2f}亿" if profit_upper else "-"
            )
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


# ============================================================================
# 第 5 轮新增 4 域数据 tab：ETF / 行业板块 / 日历 / 筹码+融资融券
# 缓存 TTL：行情 5min，IPO 日历 10min（变更频次低）
# 错误处理：API 4xx/5xx 由 _handle_response 自动调 st.error；非 dict 返回视为异常
# ============================================================================


def _render_etf_tab(symbol: str) -> None:
    """ETF 详情 tab：基本信息 + 净值曲线 + 成分股 Top10。

    只在 render() 检测到 asset_type == "etf" 时才会被调用。
    """
    st.subheader("ETF 详情")
    try:
        with st.spinner("正在拉取 ETF 数据..."):
            info: dict[str, Any] = _fetch_etf_info(symbol)
        if "error" in info:
            st.info("该标的非 ETF")
            return

        # 基本信息表（前 10 个有意义的字段，避免一次性铺 26 列）
        info_fields: list[tuple[str, str]] = [
            ("etf_type", "类型"),
            ("establish_date", "成立日期"),
            ("track_index_code", "跟踪指数代码"),
            ("track_index_name", "跟踪指数名称"),
            ("manage_institution", "管理人"),
            ("total_mv", "规模"),
            ("close_price", "收盘价"),
            ("change_pct", "涨跌幅(%)"),
            ("nav", "净值"),
            ("disc", "折溢价率(%)"),
        ]
        info_rows: list[dict[str, str]] = []
        for k, label in info_fields:
            val = info.get(k)
            if isinstance(val, float):
                if k in ("change_pct", "disc"):
                    val_str = f"{val:+.2f}%"
                elif k == "total_mv":
                    val_str = _format_number(val)
                else:
                    val_str = f"{val:.4f}".rstrip("0").rstrip(".")
            else:
                val_str = str(val) if val is not None else "-"
            info_rows.append({"字段": label, "取值": val_str})
        st.markdown("**基本信息**")
        st.dataframe(info_rows, use_container_width=True, hide_index=True)

        # 净值曲线（最近 60 期，按日期升序）
        try:
            with st.spinner("正在拉取历史净值..."):
                nav_result: dict[str, Any] = _fetch_etf_nav(symbol)
            nav_items: list[dict[str, Any]] = nav_result.get("items", [])
            if nav_items:
                st.markdown("**历史净值**")
                # 后端按 date DESC 返回，前端升序展示
                nav_items = sorted(nav_items, key=lambda x: x.get("date", ""))
                nav_df_rows: list[dict[str, Any]] = [
                    {"date": r.get("date", ""), "净值": r.get("nav")} for r in nav_items
                ]
                st.line_chart(nav_df_rows, x="date", y="净值", height=240)
        except Exception as e:
            st.warning(f"历史净值加载失败: {e}")

        # 成分股 Top 10
        try:
            with st.spinner("正在拉取成分股..."):
                holdings_result: dict[str, Any] = _fetch_etf_holdings(symbol)
            holdings: list[dict[str, Any]] = holdings_result.get("items", [])
            if holdings:
                st.markdown("**成分股 Top 10**")
                top10_rows: list[dict[str, Any]] = [
                    {
                        "代码": h.get("constituent_code", "-"),
                        "名称": h.get("constituent_name", "-"),
                        "权重(%)": f"{h.get('ratio', 0):.2f}"
                        if h.get("ratio") is not None
                        else "-",
                    }
                    for h in holdings[:10]
                ]
                st.dataframe(top10_rows, use_container_width=True, hide_index=True)
            else:
                st.info("暂无成分股数据")
        except Exception as e:
            st.warning(f"成分股加载失败: {e}")
    except Exception as e:
        st.warning(f"ETF 数据加载失败: {e}")


def _render_sectors_tab() -> None:
    """行业板块 tab：板块涨跌幅榜 + 热门板块 Top 10。"""
    st.subheader("行业板块")
    try:
        with st.spinner("正在拉取板块数据..."):
            board_result: dict[str, Any] = _fetch_sectors_board()
        if "error" in board_result:
            return
        items: list[dict[str, Any]] = board_result.get("items", [])
        if not items:
            st.info(
                "暂无板块数据，请先触发板块采集（POST /api/v1/data/sectors/refresh）"
            )
            return

        # 按 sector_type 分桶渲染
        by_type: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            by_type.setdefault(it.get("sector_type", "unknown"), []).append(it)

        if "industry" in by_type:
            st.markdown("**行业涨幅榜 Top 10**")
            rows: list[dict[str, Any]] = []
            for it in sorted(
                by_type["industry"],
                key=lambda x: x.get("change_pct") or 0,
                reverse=True,
            )[:10]:
                pct: float | None = it.get("change_pct")
                rows.append(
                    {
                        "板块": it.get("name", "-"),
                        "涨跌幅(%)": f"{pct:+.2f}" if pct is not None else "-",
                        "领涨股": it.get("lead_stock", "-") or "-",
                        "主力净流入": _format_number(it.get("main_net_inflow")),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)

        if "fund_flow" in by_type:
            st.markdown("**资金流入 Top 5**")
            rows_ff: list[dict[str, Any]] = []
            for it in sorted(
                by_type["fund_flow"],
                key=lambda x: x.get("main_net_inflow") or 0,
                reverse=True,
            )[:5]:
                rows_ff.append(
                    {
                        "板块": it.get("name", "-"),
                        "主力净流入": _format_number(it.get("main_net_inflow")),
                        "5日主力净流入": _format_number(it.get("main_net_inflow_5d")),
                    }
                )
            st.dataframe(rows_ff, use_container_width=True, hide_index=True)

        if "concept" in by_type:
            st.markdown("**概念涨幅榜 Top 5**")
            rows_c: list[dict[str, Any]] = []
            for it in sorted(
                by_type["concept"], key=lambda x: x.get("change_pct") or 0, reverse=True
            )[:5]:
                pct = it.get("change_pct")
                rows_c.append(
                    {
                        "概念": it.get("name", "-"),
                        "涨跌幅(%)": f"{pct:+.2f}" if pct is not None else "-",
                    }
                )
            st.dataframe(rows_c, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"板块数据加载失败: {e}")

    # 热门板块
    try:
        with st.spinner("正在拉取热门板块..."):
            hot_result: dict[str, Any] = _fetch_sectors_hot()
        if "error" in hot_result:
            return
        hot_items: list[dict[str, Any]] = hot_result.get("items", [])
        if hot_items:
            st.markdown("**热门板块 Top 10**")
            hot_rows: list[dict[str, Any]] = []
            for it in hot_items[:10]:
                pct = it.get("change_pct")
                hot_rows.append(
                    {
                        "排名": it.get("rank", "-"),
                        "板块": it.get("name", "-"),
                        "涨跌幅(%)": f"{pct:+.2f}" if pct is not None else "-",
                        "领涨股": it.get("lead_stock", "-") or "-",
                    }
                )
            st.dataframe(hot_rows, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"热门板块加载失败: {e}")


def _render_calendar_tab(symbol: str) -> None:
    """日历 tab：港股 IPO 日历（默认） + 该标的 exdiv 日历。"""
    st.subheader("日历")
    st.caption("IPO 数据源仅 hk/us 可用（A 股源已停）；exdiv 按 symbol 查。")

    market_choice: str = st.radio(
        "IPO 市场",
        options=["hk", "us"],
        index=0,
        horizontal=True,
        help="选择 IPO 日历的市场（港股/美股）",
        key=f"ipo_market_{symbol}",
    )

    try:
        with st.spinner("正在拉取 IPO 日历..."):
            ipo_result: dict[str, Any] = _fetch_ipo_calendar(market_choice)
        if "error" in ipo_result:
            return
        ipo_items: list[dict[str, Any]] = ipo_result.get("items", [])
        if not ipo_items:
            st.info(f"{market_choice.upper()} 市场暂无 IPO 日历数据，请先触发采集")
        else:
            st.markdown(
                f"**{market_choice.upper()} IPO 日历（最近 {len(ipo_items)} 条）**"
            )
            ipo_rows: list[dict[str, Any]] = [
                {
                    "事件日期": it.get("event_date", "-"),
                    "代码": it.get("symbol", "-") or "-",
                    "名称": it.get("name", "-") or "-",
                    "阶段": it.get("stage", "-") or "-",
                    "发行价": f"{it.get('price'):.2f}"
                    if it.get("price") is not None
                    else "-",
                }
                for it in ipo_items[:30]
            ]
            st.dataframe(ipo_rows, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"IPO 日历加载失败: {e}")

    st.divider()
    st.markdown(f"**{symbol} 除权日历**")
    try:
        with st.spinner("正在拉取除权日历..."):
            exdiv_result: dict[str, Any] = _fetch_exdiv_calendar(symbol)
        if "error" in exdiv_result:
            st.info("该标的暂无除权数据（A 股源已停）")
            return
        exdiv_items: list[dict[str, Any]] = exdiv_result.get("items", [])
        if not exdiv_items:
            st.info("该标的暂无除权数据")
            return
        exdiv_rows: list[dict[str, Any]] = [
            {
                "除权日": it.get("event_date", "-"),
                "代码": it.get("symbol", "-") or "-",
                "名称": it.get("name", "-") or "-",
                "每股分红": f"{it.get('dividend_per_share'):.4f}"
                if it.get("dividend_per_share") is not None
                else "-",
                "币种": it.get("currency", "-") or "-",
                "派息日": it.get("pay_date", "-") or "-",
            }
            for it in exdiv_items
        ]
        st.dataframe(exdiv_rows, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"除权日历加载失败: {e}")


def _render_chip_tab(symbol: str) -> None:
    """筹码/融资融券 tab：最新一期 90/70 集中度 + 历史曲线。"""
    st.subheader("筹码 / 融资融券")
    st.caption("chip / margintrade 数据源仅 A 股（sh/sz/bj）可用")

    try:
        with st.spinner("正在拉取筹码数据..."):
            chip_result: dict[str, Any] = _fetch_chip(symbol)
        if "error" in chip_result:
            st.info("该标的暂无筹码数据（非 A 股 / 未采集）")
            return
        chip_items: list[dict[str, Any]] = chip_result.get("items", [])
        if not chip_items:
            st.info("暂无筹码数据")
            return

        latest: dict[str, Any] = chip_items[0]  # 后端按 date DESC 返回
        st.markdown(f"**最新一期 ({latest.get('date', '-')})**")

        c90: float | None = latest.get("chip_concentration_90")
        c70: float | None = latest.get("chip_concentration_70")
        avg_cost: float | None = latest.get("chip_avg_cost")
        profit_rate: float | None = latest.get("chip_profit_rate")
        close: float | None = latest.get("close_price")

        # 数字大字号展示 90/70 集中度；用 st.metric（▲/▼ 前缀覆盖颜色盲）
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric(
                "90% 成本集中度",
                f"{c90:.2f}" if c90 is not None else "-",
                help="90% 筹码分布的价格区间宽度，越小越集中",
            )
        with mc2:
            st.metric(
                "70% 成本集中度",
                f"{c70:.2f}" if c70 is not None else "-",
                help="70% 筹码分布的价格区间宽度",
            )
        with mc3:
            st.metric("平均成本", f"{avg_cost:.2f}" if avg_cost is not None else "-")
        with mc4:
            # 颜色盲友好：涨/跌用 ▲/▼ 文本前缀而非纯红绿
            if profit_rate is not None:
                arrow: str = "▲" if profit_rate >= 0 else "▼"
                st.metric("获利比例", f"{arrow} {abs(profit_rate):.1f}%")
            else:
                st.metric("获利比例", "-")

        if close is not None and avg_cost is not None and avg_cost > 0:
            spread: float = (close - avg_cost) / avg_cost * 100
            arrow_spread: str = "▲" if spread >= 0 else "▼"
            st.metric(
                "现价 vs 成本",
                f"{arrow_spread} {abs(spread):+.2f}%",
                help=f"收盘价 {close:.2f} vs 平均成本 {avg_cost:.2f}",
            )

        # 历史曲线（近 10 期）
        if len(chip_items) > 1:
            st.markdown("**近 10 期集中度趋势**")
            history: list[dict[str, Any]] = list(reversed(chip_items[-10:]))
            chart_rows: list[dict[str, Any]] = [
                {
                    "date": r.get("date", ""),
                    "90% 集中度": r.get("chip_concentration_90"),
                    "70% 集中度": r.get("chip_concentration_70"),
                }
                for r in history
            ]
            st.line_chart(
                chart_rows, x="date", y=["90% 集中度", "70% 集中度"], height=240
            )
    except Exception as e:
        st.warning(f"筹码数据加载失败: {e}")
