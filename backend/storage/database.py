from contextlib import contextmanager
from typing import Generator

import sqlite3

from loguru import logger

from backend.config import get_config, get_data_dir

_db_path_override: str | None = None


def set_db_path(path: str | None) -> None:
    global _db_path_override
    _db_path_override = path


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = _db_path_override
    if db_path is None:
        config = get_config()
        db_path = str(get_data_dir() / config["database"]["path"])
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    logger.info("数据库连接已建立: {}", db_path)
    return conn


@contextmanager
def get_db(db_path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("数据库操作异常，已回滚")
        raise
    finally:
        conn.close()
        logger.info("数据库连接已关闭")
