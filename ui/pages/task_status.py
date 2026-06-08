from typing import Any

import streamlit as st

from ui.api_client import get_task_status, get_task_logs, trigger_task

# 注意：键名必须与后端 scheduler/jobs.py 中的 VALID_TASK_NAMES 完全一致
TASK_LABELS: dict[str, str] = {
    "quote": "行情采集",
    "daily_close": "日收盘采集",
    "news": "新闻采集",
    "ai_report": "AI 报告生成",
}


@st.cache_data(ttl=15)
def _fetch_task_status() -> dict[str, Any]:
    """缓存任务状态结果，避免每次 Streamlit 重新渲染都打后端。"""
    return get_task_status()


def render() -> None:
    st.header("任务运行状态")

    st.subheader("任务概览")
    try:
        status_result: dict[str, Any] = _fetch_task_status()
        items: list[dict[str, Any]] = status_result.get("items", [])

        if not items:
            st.info("暂无任务信息")
        else:
            for task in items:
                name: str = task.get("task_name", task.get("name", ""))
                label: str = TASK_LABELS.get(name, name)
                status: str = task.get("status", task.get("next_run_time", ""))
                nc1, nc2, nc3 = st.columns(3)
                with nc1:
                    st.markdown(f"**{label}**")
                    st.caption(name)
                with nc2:
                    st.text(f"状态: {status}")
                with nc3:
                    if name in TASK_LABELS:
                        if st.button("手动触发", key=f"trigger_{name}"):
                            try:
                                trigger_task(name)
                                st.success(f"已触发: {label}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"触发失败: {e}")
                st.divider()
    except Exception as e:
        st.warning(f"任务状态加载失败: {e}")

    st.subheader("运行日志")
    col1, col2 = st.columns(2)
    with col1:
        log_task_name: str = st.selectbox(
            "任务名称", ["全部"] + list(TASK_LABELS.keys()), key="log_task"
        )
    with col2:
        log_status: str = st.selectbox(
            "状态", ["全部", "success", "failure", "skipped"], key="log_status"
        )

    try:
        log_params: dict[str, Any] = {"page_size": 20}
        if log_task_name != "全部":
            log_params["task_name"] = log_task_name
        if log_status != "全部":
            log_params["status"] = log_status
        log_result: dict[str, Any] = get_task_logs(**log_params)
        log_items: list[dict[str, Any]] = log_result.get("items", [])
        if not log_items:
            st.info("暂无运行日志")
            return
        for log in log_items:
            lc1, lc2, lc3, lc4, lc5 = st.columns([1.5, 1, 1, 1.5, 2])
            with lc1:
                task_label: str = TASK_LABELS.get(
                    log.get("task_name", ""), log.get("task_name", "-")
                )
                st.text(task_label)
            with lc2:
                log_s: str = log.get("status", "-")
                color: str = {
                    "success": "green",
                    "failure": "red",
                    "skipped": "orange",
                }.get(log_s, "gray")
                st.markdown(f":{color}[{log_s}]")
            with lc3:
                st.text(f"标的: {log.get('affected_assets', '-')}")
            with lc4:
                st.text(str(log.get("started_at", "-"))[:16])
            with lc5:
                err: str = log.get("error_message", "")
                if err:
                    with st.expander("错误"):
                        st.text(err)
            st.divider()
    except Exception as e:
        st.warning(f"运行日志加载失败: {e}")
