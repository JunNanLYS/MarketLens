from typing import Any

import streamlit as st

from ui.api_client import get_reports, generate_reports

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

RISK_LABELS: dict[str, str] = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _render_report_card(report: dict[str, Any], index: int) -> None:
    action: str = report.get("action", "")
    confidence: float | None = report.get("confidence")
    risk_level: str = report.get("risk_level", "")
    summary: str = report.get("summary", "")
    symbol: str = report.get("symbol", "")
    name: str = report.get("name", symbol)
    generated_at: str = report.get("generated_at", "")

    color: str = ACTION_COLORS.get(action, "gray")
    label: str = ACTION_LABELS.get(action, action)

    with st.container():
        header_cols = st.columns([3, 1, 1, 1])
        with header_cols[0]:
            st.markdown(f"**{symbol}** — {name}")
        with header_cols[1]:
            st.markdown(f":{color}[**{label}**]")
        with header_cols[2]:
            if confidence is not None:
                st.progress(min(confidence, 1.0))
                st.caption(f"{confidence:.0%}")
        with header_cols[3]:
            st.caption(f"风险: {RISK_LABELS.get(risk_level, risk_level)}")

        st.markdown(f"> {summary}")

        with st.expander("查看详情", key=f"report_detail_{index}"):
            bullish: list[str] = report.get("bullish_reasons", [])
            bearish: list[str] = report.get("bearish_reasons", [])
            key_risks: list[str] = report.get("key_risks", [])
            data_used: list[dict[str, Any]] = report.get("data_used", [])

            col1, col2 = st.columns(2)
            with col1:
                if bullish:
                    st.markdown("**🟢 看多理由**")
                    for reason in bullish:
                        st.markdown(f"- {reason}")
            with col2:
                if bearish:
                    st.markdown("**🔴 看空理由**")
                    for reason in bearish:
                        st.markdown(f"- {reason}")

            if key_risks:
                st.markdown("**⚠️ 关键风险**")
                for risk in key_risks:
                    st.markdown(f"- {risk}")

            if data_used:
                st.markdown("**📎 数据溯源**")
                for du in data_used:
                    st.markdown(
                        f"- `{du.get('source', '')}` / {du.get('type', '')} — {du.get('collected_at', '')}"
                    )

        st.caption(f"生成时间: {generated_at}")
        st.divider()


def render() -> None:
    st.header("AI 报告")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        date_filter: str = st.date_input("日期", value=None, key="report_date")
    with col2:
        action_filter: str = st.selectbox(
            "动作建议",
            ["全部", "buy", "sell", "watch", "avoid"],
            key="report_action",
        )
    with col3:
        risk_filter: str = st.selectbox(
            "风险等级",
            ["全部", "low", "medium", "high"],
            key="report_risk",
        )
    with col4:
        st.write("")
        st.write("")
        if st.button("🔄 手动生成报告"):
            result: dict[str, Any] = generate_reports()
            if result.get("status") == "accepted":
                st.success(f"报告生成已提交，预计 {result.get('estimated_seconds', 0)} 秒完成")

    params: dict[str, Any] = {"page_size": 50}
    if date_filter:
        params["date"] = str(date_filter)
    if action_filter != "全部":
        params["action"] = action_filter
    if risk_filter != "全部":
        params["risk_level"] = risk_filter

    result: dict[str, Any] = get_reports(**params)
    items: list[dict[str, Any]] = result.get("items", [])

    if not items:
        st.info("暂无 AI 报告")
        return

    page_info: dict[str, Any] = result.get("page_info", {})
    total: int = page_info.get("total", len(items))
    st.caption(f"共 {total} 份报告")

    for i, report in enumerate(items):
        _render_report_card(report, i)
