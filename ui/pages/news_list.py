from typing import Any

import streamlit as st
from loguru import logger

from ui.api_client import get_news

SENTIMENT_DISPLAY: dict[str, tuple[str, str]] = {
    "positive": ("正面", "green"),
    "negative": ("负面", "red"),
    "neutral": ("中性", "gray"),
}


@st.cache_data(ttl=60)
def _fetch_news(_symbol: str, _days: int, _sentiment: str) -> dict[str, Any]:
    """获取新闻列表（缓存 60s）。

    必须在模块作用域：嵌套 def 会随每次 rerun 创建新函数对象，
    导致 st.cache_data 用函数身份做 key 时无法命中/无法 clear。
    """
    params: dict[str, Any] = {"days": _days, "page_size": 50}
    if _symbol.strip():
        params["symbol"] = _symbol.strip()
    if _sentiment != "全部":
        params["sentiment"] = _sentiment
    return get_news(**params)


def render() -> None:
    st.header("新闻列表")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_filter: str = st.text_input("标的代码", key="news_symbol")
    with col2:
        days: int = st.selectbox(
            "时间范围（天）", [1, 3, 7, 14, 30], index=2, key="news_days"
        )
    with col3:
        sentiment: str = st.selectbox(
            "情绪", ["全部", "positive", "negative", "neutral"], key="news_sentiment"
        )

    try:
        result: dict[str, Any] = _fetch_news(symbol_filter, days, sentiment)
        items: list[dict[str, Any]] = result.get("items", [])
        total: int = result.get("total", 0)
        st.caption(f"共 {total} 条新闻")

        if not items:
            st.info("暂无新闻数据")
            return

        for news in items:
            with st.container():
                nc1, nc2, nc3 = st.columns([6, 2, 1])
                with nc1:
                    title: str = news.get("title", "")
                    st.markdown(f"**{title}**")
                    symbols: list[str] = news.get("related_symbols", [])
                    if symbols:
                        st.caption(f"关联标的: {', '.join(symbols)}")
                with nc2:
                    source: str = news.get("source", "-")
                    st.caption(f"来源: {source}")
                with nc3:
                    sentiment_val: str = news.get("sentiment", "")
                    if sentiment_val:
                        label, color = SENTIMENT_DISPLAY.get(
                            sentiment_val, (sentiment_val, "gray")
                        )
                        st.markdown(f":{color}[{label}]")
                published: str = news.get("published_at", "")
                if published:
                    st.caption(f"发布时间: {published}")
                st.divider()
    except Exception:
        logger.exception("新闻加载失败")
        st.warning("新闻加载失败，请稍后重试")
