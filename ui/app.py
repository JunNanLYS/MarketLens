import time

import streamlit as st

from ui.api_client import check_health
from ui.pages import tracked_assets, asset_detail, ai_reports, portfolio


def _cached_health_check() -> bool:
    now = time.time()
    last_check = st.session_state.get("health_check_time", 0)
    if now - last_check < 30:
        return st.session_state.get("health_check_result", False)
    result = check_health()
    st.session_state["health_check_time"] = now
    st.session_state["health_check_result"] = result
    return result

st.set_page_config(
    page_title="MarketLens",
    page_icon="📊",
    layout="wide",
)

PAGES: dict[str, str] = {
    "追踪标的": "tracked",
    "标的详情": "detail",
    "AI 报告": "reports",
    "投资组合": "portfolio",
}

with st.sidebar:
    st.title("📊 MarketLens")
    st.divider()
    selected_label: str = st.radio("导航", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    if _cached_health_check():
        st.success("API 已连接")
    else:
        st.error("API 连接失败")
    st.caption("http://localhost:8000")

page_key: str = PAGES[selected_label]

if page_key == "tracked":
    tracked_assets.render()
elif page_key == "detail":
    asset_detail.render()
elif page_key == "reports":
    ai_reports.render()
elif page_key == "portfolio":
    portfolio.render()
