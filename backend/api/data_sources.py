"""数据源状态查询端点。

仅做"显式可观察":从 config 读配置 + 调 NeoDataClient 拿 token 状态,
不在请求时构造 Provider 实例（避免服务实例重建的 Known issue 加剧）。

设计原则:
- GET 无副作用
- 错误响应统一为 {"error": "...", "detail": "..."}
"""
from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter

from backend.collectors.neodata_client import NeoDataClient
from backend.config import get_config

router = APIRouter(prefix="/api/v1/data-sources", tags=["data-sources"])


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def _build_neo_client() -> NeoDataClient:
    """从 config 读取 NeoData 配置并构造一个轻量客户端。

    注意:不会触发任何网络请求;TokenManager 也不连接远端,
    只读本地 ~/.workbuddy/.neodata_token 缓存。
    """
    config = get_config()
    data_sources = config.get("data_sources", {})
    sources: list[dict] = (
        list(data_sources.get("structured", []))
        + list(data_sources.get("news", []))
    )
    neodata_cfg = next(
        (s for s in sources if s.get("provider") == "NeoDataProvider"),
        {},
    )
    params = neodata_cfg.get("params") or {}
    return NeoDataClient(
        endpoint=params.get(
            "endpoint", "https://copilot.tencent.com/agenttool/v1/neodata"
        ),
        config_token=params.get("token") or None,
        timeout=neodata_cfg.get("timeout", 30),
    )


def _describe_neo_data(cfg: dict) -> dict[str, Any]:
    """聚合 NeoData 源的状态:配置可见性 + token 健康度。"""
    client = _build_neo_client()
    try:
        status = client.get_token_status()
    except Exception:
        # TokenManager 自身只读本地文件,理论上不会抛;
        # 这里兜底避免状态端点把"读状态"这件事做崩。
        status = {
            "has_token": False,
            "source": "none",
            "expires_at": None,
            "verified": False,
        }
    return {
        "configured": bool(cfg.get("enabled", True)),
        "optional": bool(cfg.get("optional", False)),
        "endpoint": (cfg.get("params") or {}).get("endpoint"),
        "has_token": status.get("has_token", False),
        "token_source": status.get("source"),
        "token_expires_at": status.get("expires_at"),
        "token_verified": status.get("verified", False),
    }


def _describe_westock(cfg: dict) -> dict[str, Any]:
    """WeStock 的 command 字段在配置里是完整命令行,首项是真实可执行文件。"""
    params = cfg.get("params") or {}
    command: str = params.get("command", "")
    executable: str | None = None
    resolved: bool = False
    if command:
        first = command.split()[0] if command.split() else ""
        executable = first or None
        if executable:
            resolved = shutil.which(executable) is not None
    return {
        "configured": bool(cfg.get("enabled", True)),
        "optional": bool(cfg.get("optional", False)),
        "command": command or None,
        "executable": executable,
        "command_resolved": resolved,
    }


def _describe_http_source(cfg: dict) -> dict[str, Any]:
    """通用 HTTP/RSS/新闻源:暴露 endpoint/url,不做连通性检查。"""
    params = cfg.get("params") or {}
    return {
        "configured": bool(cfg.get("enabled", True)),
        "optional": bool(cfg.get("optional", False)),
        "endpoint": params.get("endpoint") or params.get("url"),
    }


def _describe_one_source(category: str, cfg: dict) -> dict[str, Any]:
    provider: str = cfg.get("provider", "")
    if provider == "NeoDataProvider":
        return _describe_neo_data(cfg)
    if provider == "WeStockProvider":
        return _describe_westock(cfg)
    return _describe_http_source(cfg)


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------

@router.get("/status", summary="查询所有数据源的配置与健康状态")
def get_data_sources_status() -> dict:
    config = get_config()
    data_sources: dict = config.get("data_sources", {})

    structured: list[dict] = [
        _describe_one_source("structured", s)
        | {"name": s.get("name"), "provider": s.get("provider")}
        for s in data_sources.get("structured", [])
    ]
    news: list[dict] = [
        _describe_one_source("news", s)
        | {"name": s.get("name"), "provider": s.get("provider")}
        for s in data_sources.get("news", [])
    ]

    return {
        "structured": structured,
        "news": news,
        "hint": "NeoData token 由外部 workbuddy 工具管理,本项目只读。",
    }
