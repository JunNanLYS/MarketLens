from functools import lru_cache
from pathlib import Path

import yaml
from loguru import logger

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_CONFIG_PATH: Path = _PROJECT_ROOT / "config.yaml"
_DATA_DIR: Path = _PROJECT_ROOT / "data"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_config() -> dict:
    """??????????config.yaml??

    ?? lru_cache ????????????????????

    Returns:
        ?????

    Raises:
        FileNotFoundError: ????????
    """
    if not _CONFIG_PATH.exists():
        logger.error("配置文件不存在: {}", _CONFIG_PATH)
        raise FileNotFoundError(f"配置文件不存在: {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        config: dict = yaml.safe_load(f)
    logger.info("已加载配置文件: {}", _CONFIG_PATH)
    return config


def get_project_root() -> Path:
    """??????????

    Returns:
        ?????? Path ???
    """
    return _PROJECT_ROOT


def get_data_dir() -> Path:
    """????????????

    Returns:
        ????? Path ???
    """
    _ensure_data_dir()
    return _DATA_DIR
