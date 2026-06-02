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
    logger.debug("数据库连接已建立: {}", db_path)
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
        logger.debug("数据库连接已关闭")


def query_run_logs(
    task_name: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """?? run_logs ????????? tasks API ? scheduler ???"""
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
