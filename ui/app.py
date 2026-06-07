import streamlit as st

from ui.api_client import check_health
from ui.pages import tracked_assets, asset_detail, ai_reports, portfolio, news_list, task_status, settings


@st.cache_data(ttl=30)
def _cached_health_check() -> bool:
    # 30s TTL 跨用户/跨 session 复用：避免每个新用户首次访问都打 /health。
    # Streamlit rerun 也只每 30s 重新检查。
    return check_health()

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
    "新闻列表": "news",
    "任务状态": "status",
    "系统配置": "settings",
}

with st.sidebar:
    st.title("📊 MarketLens")
    st.divider()
    # 可访问性：保留可见标签 "导航"，屏幕阅读器能识别侧栏主导航控件（ISSUES.md MINOR）。
    st.caption("导航")
    selected_label: str = st.radio("导航", list(PAGES.keys()), label_visibility="visible")
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
elif page_key == "news":
    news_list.render()
elif page_key == "status":
    task_status.render()
elif page_key == "settings":
    settings.render()
