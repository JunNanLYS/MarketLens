from typing import Any

import streamlit as st

from ui.api_client import get_data_sources_config, get_task_status


@st.cache_data(ttl=60)
def _fetch_data_sources() -> list[dict[str, Any]]:
    """通过 FastAPI 端点获取数据源配置。

    原先直读 config.yaml 违反 CLAUDE.md Module boundaries 约束
    （ui/ 严禁 import backend/storage/,也禁止直读 config.yaml）。
    现改为调用 ``GET /api/v1/data-sources/config``,与后端解耦。
    """
    try:
        result: dict[str, Any] = get_data_sources_config()
        return list(result.get("structured", [])) + list(result.get("news", []))
    except Exception:
        return []


def render() -> None:
    st.header("系统配置")

    st.subheader("数据源状态")
    try:
        data_sources: list[dict[str, Any]] = _fetch_data_sources()
        if data_sources:
            for ds in data_sources:
                dc1, dc2, dc3 = st.columns([2, 1, 1])
                with dc1:
                    name: str = ds.get("name", ds.get("provider", "-"))
                    st.markdown(f"**{name}**")
                with dc2:
                    st.text(f"类型: {ds.get('type', '-')}")
                with dc3:
                    enabled: bool = ds.get("enabled", ds.get("optional", True))
                    st.text("启用" if enabled else "停用")
                st.divider()
        else:
            st.info("未找到数据源配置")
    except Exception as e:
        st.warning(f"配置文件读取失败: {e}")

    st.subheader("调度任务频率")
    try:
        status_result: dict[str, Any] = get_task_status()
        items: list[dict[str, Any]] = status_result.get("items", [])
        for task in items:
            sc1, sc2 = st.columns(2)
            with sc1:
                st.text(task.get("task_name", "-"))
            with sc2:
                st.text(task.get("next_run_time", task.get("status", "-")))
    except Exception as e:
        st.warning(f"调度状态加载失败: {e}")

    st.subheader("系统信息")
    st.text("数据库: SQLite (本地)")
    st.text("数据存储: 全部本地化，无云端上传")
    st.text("AI 引擎: 规则引擎（证据驱动）")
