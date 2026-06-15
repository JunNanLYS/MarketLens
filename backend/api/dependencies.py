"""跨路由共享的 FastAPI Depends 依赖。

放在独立模块避免某个资源 router 反向依赖另一个 router 的"工具"函数；
当前包含写端点鉴权依赖 ``verify_api_key``。
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

from backend.config import get_config


def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    """写端点鉴权依赖：从配置或环境变量校验 API Key。

    优先级：环境变量 ``MARKETLENS_API_KEY`` > ``config.security.api_key``。
    本地工具默认 ``marketlens-local``（单用户场景，非互联网部署）。
    """
    config = get_config()
    expected_key: str = os.getenv("MARKETLENS_API_KEY") or config.get(
        "security", {}
    ).get("api_key", "marketlens-local")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "detail": "无效或缺失的 API Key"},
        )
