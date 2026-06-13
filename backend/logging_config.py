"""MarketLens 日志配置 —— loguru 落盘 + 终端双输出。

设计目标:
- 默认 INFO 级别(可 env `MARKETLENS_LOG_LEVEL` 调)
- 按天轮转 + 50 MB 单文件上限,保留 30 天
- 日志目录:``<项目根目录>/logs/``(与 ``backend/`` 同级的 ``logs/`` 子目录),
  不再走 ``%APPDATA%``/XDG,方便 dev 态直接 ``tail -f logs/marketlens-*.log`` 排查
- 终端输出保留颜色,方便 dev 态排查
- 落盘去掉 ANSI 颜色码,避免 cat 看时满屏乱码
- logger.add() 返回 handler_id,允许调用方后续 remove

调用范式:
    from backend.logging_config import setup_logging
    setup_logging()  # 必须在第一次 ``from loguru import logger`` 之后
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

# 项目根目录 = ``backend/logging_config.py`` 的上两级目录。
# ``Path(__file__).resolve()`` 拿到绝对路径后 ``.parent.parent`` 就是
# pyproject.toml/CLAUDE.md 所在的项目根;不依赖 ``os.getcwd()`` 避免
# 在 ``scripts/launcher.py`` / pytest / uvicorn 等不同入口下路径漂移。
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

_DEFAULT_LEVEL: str = "INFO"
_LEVEL_ENV_VAR: str = "MARKETLENS_LOG_LEVEL"
_INITIALIZED: bool = False


def _resolve_log_level() -> str:
    """解析日志级别,env var 覆盖默认 INFO。

    支持的合法值:``TRACE`` / ``DEBUG`` / ``INFO`` / ``WARNING`` / ``ERROR`` / ``CRITICAL``。
    非法值静默回退 INFO,避免启动失败。
    """
    raw = os.environ.get(_LEVEL_ENV_VAR, _DEFAULT_LEVEL).upper().strip()
    if raw in {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return raw
    return _DEFAULT_LEVEL


def _log_dir() -> Path:
    """日志目录:``<项目根目录>/logs/``。

    ``PROJECT_ROOT`` 由模块加载时基于 ``__file__`` 解析,稳健不受 cwd 影响;
    ``mkdir(parents=True, exist_ok=True)`` 保证首次启动时自动创建。
    """
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging() -> int:
    """配置 loguru:落盘(按天轮转)+ 终端(带色)。

    **幂等**:多次调用不会重复添加 handler。适用于 ``main_exe.py`` 和
    ``main.py`` 各自调一次的场景。

    Returns:
        logger.add() 返回的 handler_id(int),首次调用返回;后续返回 -1。

    Notes:
        - 测试场景下建议保持默认配置不动,本函数仅在生产/开发启动路径调用。
        - env ``MARKETLENS_LOG_LEVEL`` 可临时调级别,合法值见 _resolve_log_level。
    """
    global _INITIALIZED
    if _INITIALIZED:
        return -1
    _INITIALIZED = True

    level = _resolve_log_level()
    log_dir = _log_dir()

    # 0) 移除 loguru 默认 handler（避免与下面新加的终端 handler 重复输出）
    logger.remove()

    # 1) 落盘:按天 + 50 MB 切分,保留 30 天,UTF-8,无 ANSI 颜色
    logger.add(
        str(log_dir / "marketlens-{time:YYYY-MM-DD}.log"),
        level=level,
        rotation="50 MB",       # 单文件 50 MB 切分
        retention="30 days",    # 30 天前的清理
        compression=None,       # 不压(本地磁盘宽裕;压了反而 cat 麻烦)
        encoding="utf-8",
        enqueue=True,           # 异步写,避免 IO 阻塞 event loop
        backtrace=True,
        diagnose=False,         # 关 diagnose 避免泄漏敏感变量
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    # 2) 终端:带颜色,同等级,异步队列
    logger.add(
        sys.stderr,
        level=level,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    logger.info(
        "日志初始化完成: level={}, file={}, retention=30d, rotation=50MB",
        level,
        log_dir,
    )
    return 0

