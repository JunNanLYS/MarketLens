from typing import Any

import streamlit as st
from loguru import logger

from ui.api_client import get_news
from ui.api_client import get_assets

SENTIMENT_LABELS: dict[str, str] = {
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
}


def render() -> None:
    st.header("新闻列表")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_filter: str = st.text_input("标的代码", key="news_symbol")
    with col2:
        days: int = st.selectbox("时间范围（天）", [1, 3, 7, 14, 30], index=2, key="news_days")
    with col3:
        sentiment: str = st.selectbox(
            "情绪", ["全部", "positive", "negative", "neutral"], key="news_sentiment"
        )

    params: dict[str, Any] = {"days": days, "page_size": 50}
    if symbol_filter.strip():
        params["symbol"] = symbol_filter.strip()
    if sentiment != "全部":
        params["sentiment"] = sentiment

    try:
        result: dict[str, Any] = get_news(**params)
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
                        color: str = {"positive": "green", "negative": "red"}.get(sentiment_val, "gray")
                        label: str = SENTIMENT_LABELS.get(sentiment_val, sentiment_val)
                        st.markdown(f":{color}[{label}]")
                published: str = news.get("published_at", "")
                if published:
                    st.caption(f"发布时间: {published}")
                st.divider()
    except Exception:
        logger.exception("新闻加载失败")
        st.warning("新闻加载失败，请稍后重试")