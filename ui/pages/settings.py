from pathlib import Path
from typing import Any

import streamlit as st

from ui.api_client import get_task_status


def render() -> None:
    st.header("系统配置")

    st.subheader("数据源状态")
    try:
        import yaml
        config_path: Path = Path(__file__).resolve().parents[2] / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f)
        data_sources: list[dict[str, Any]] = config.get("data_sources", [])
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
    st.text(f"数据库: SQLite (本地)")
    st.text(f"数据存储: 全部本地化，无云端上传")
    st.text(f"AI 引擎: 规则引擎（证据驱动）")