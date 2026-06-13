"""可编辑配置端点：GET 返回当前可编辑项 + 描述，PATCH 应用 diff 并立即生效。

YAML 结构：data_sources.news / structured 是 list of dicts，每个 dict 含 name/enabled/optional/timeout。
前端 key 格式：data_sources.<group>.<name>  →  整条 source dict（替换式）
              scheduler.tasks.<task>.<field>  →  标量值
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config_runtime import ConfigStoreError, get_config_store

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    """前端提交的更新：dotted-key → value 映射。

    key 形如：
    - data_sources.structured.sina          → dict {enabled, timeout, ...}（整条替换）
    - scheduler.tasks.quote.interval        → int
    """

    updates: dict[str, Any] = Field(
        ...,
        description="形如 {'data_sources.structured.sina': {enabled: false, timeout: 30}} 的 diff",
    )


def _flatten_sources(cfg: dict) -> list[dict]:
    """把 data_sources.{news,structured} 拍平成扁平行列表，方便前端渲染表格。"""
    out: list[dict] = []
    ds = cfg.get("data_sources", {})
    for group in ("structured", "news"):
        items = ds.get(group, [])
        if not isinstance(items, list):
            continue
        for src in items:
            if not isinstance(src, dict):
                continue
            out.append(
                {
                    "group": group,
                    "name": str(src.get("name", "")),
                    "provider": str(src.get("provider", "")),
                    "enabled": bool(src.get("enabled", False)),
                    "optional": bool(src.get("optional", False)),
                    "timeout": int(src.get("timeout", 30)),
                }
            )
    return out


def _list_editable(cfg: dict) -> dict:
    """组装给前端展示的"可编辑项"快照。

    关键点：仅返回白名单内的 key，避免把不相关配置（如 security.cors_origins）暴露给前端。
    """
    scheduler_tasks = cfg.get("scheduler", {}).get("tasks", {})

    return {
        "sources": _flatten_sources(cfg),
        "scheduler": {
            "tasks": {
                name: {
                    "interval": (task.get("interval") if "interval" in task else None),
                    "cron": (task.get("cron") if "cron" in task else None),
                }
                for name, task in scheduler_tasks.items()
            }
        },
    }


@router.get("")
def get_settings() -> dict:
    store = get_config_store()
    return {"editable": _list_editable(store.snapshot())}


@router.patch("")
def update_settings(body: SettingsUpdate) -> dict:
    """应用 diff。

    支持两类 key：
    1. data_sources.<group>.<name>    → 整条 source dict（list of dicts 替换）
    2. scheduler.tasks.<task>.<field>  → 标量值
    """
    store = get_config_store()
    try:
        new_cfg = store.update_with_special_handling(body.updates)
    except ConfigStoreError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_SETTING", "detail": str(exc)},
        ) from exc
    return {"editable": _list_editable(new_cfg)}


@router.post("/rollback")
def rollback_settings() -> dict:
    """从 .bak 恢复最近一次修改前的 config.yaml，并触发 reload。"""
    store = get_config_store()
    try:
        new_cfg = store.rollback_from_backup()
    except ConfigStoreError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "ROLLBACK_FAILED", "detail": str(exc)},
        ) from exc
    return {"editable": _list_editable(new_cfg)}
