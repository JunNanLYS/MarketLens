import sqlite3
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

import aiosqlite

from loguru import logger

from backend.config import get_config, get_data_dir

_db_path_override: str | None = None
_db_path_lock = threading.Lock()


def set_db_path(path: str | None) -> None:
    global _db_path_override
    with _db_path_lock:
        _db_path_override = path


def get_connection_sync(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = _db_path_override
    if db_path is None:
        config = get_config()
        db_path = str(get_data_dir() / config["database"]["path"])
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # busy_timeout 让 SQLite 在持有锁时自动等待而非立即抛 OperationalError，
    # 避免多线程并发写场景下被 fast-fail
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    logger.debug("数据库连接已建立: {}", db_path)
    return conn


@contextmanager
def get_db(db_path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection_sync(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("数据库操作异常，已回滚")
        raise
    finally:
        conn.close()
        logger.debug("数据库连接已关闭")


async def aget_connection(db_path: str | None = None) -> aiosqlite.Connection:
    """异步获取数据库连接。"""
    effective = db_path
    if effective is None:
        with _db_path_lock:
            effective = _db_path_override
    if effective is None:
        config = get_config()
        effective = str(get_data_dir() / config["database"]["path"])
    conn = await aiosqlite.connect(effective, timeout=5.0)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = aiosqlite.Row
    logger.debug("异步数据库连接已建立: {}", effective)
    return conn


@asynccontextmanager
async def aget_db(
    db_path: str | None = None,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """异步数据库上下文管理器。"""
    conn = await aget_connection(db_path)
    try:
        yield conn
        await conn.commit()
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            logger.warning("回滚操作失败，连接可能已断开")
        logger.exception("数据库操作异常，已回滚")
        raise
    finally:
        try:
            await conn.close()
        except Exception:
            logger.warning("关闭连接时发生异常")
        logger.debug("数据库连接已关闭")


def query_run_logs(
    task_name: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询 run_logs 表，供 tasks API 和 scheduler 调用。"""
    conditions: list[str] = []
    params: list[str | int] = []
    if task_name is not None:
        conditions.append("task_name = ?")
        params.append(task_name)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    where_clause: str = "" if not conditions else "WHERE " + " AND ".join(conditions)
    with get_db() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM run_logs {where_clause}",
            params,
        ).fetchone()
        total: int = count_row["cnt"] if count_row else 0
        offset: int = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT id, task_name, status, started_at, finished_at,
                       error_message, affected_assets
                FROM run_logs
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()
    items: list[dict] = [dict(row) for row in rows]
    return {
        "items": items,
        "page_info": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        },
    }
