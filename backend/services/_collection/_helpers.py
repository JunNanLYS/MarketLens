"""Helpers for CollectionService: raw data persistence, run log, decorator."""

import sqlite3

from loguru import logger

from backend.storage.database import get_db


def _with_run_log(task_name: str):
    """装饰器：为 collect_* 方法自动写 run_logs 行。

    - started_at / finished_at 记录 UTC
    - status: 成功且有数据 → "success"；返回 None（所有 provider 失败）→ "failure"；
              异常 → "failure" + error_message
    - affected_assets: 1（按 symbol/market 单点调用；collect_quotes 走原路径不适用）
    """

    def decorator(coro):
        async def wrapper(self, *args, **kwargs):
            started_at = self._now_iso()
            status = "success"
            error_message: str | None = None
            result = None
            try:
                result = await coro(self, *args, **kwargs)
                if result is None:
                    status = "failure"
                    error_message = "所有数据源均失败"
                return result
            except Exception as e:
                status = "failure"
                error_message = str(e)[:500]
                raise
            finally:
                finished_at = self._now_iso()
                try:
                    with get_db() as conn:
                        self._write_run_log(
                            conn,
                            task_name,
                            status,
                            started_at,
                            finished_at,
                            error_message,
                            1,
                        )
                except Exception as log_err:
                    logger.warning(
                        "写入 run_logs 失败: task={} err={}", task_name, log_err
                    )

        return wrapper

    return decorator


def _save_raw_data(
    conn: sqlite3.Connection,
    symbol: str | None,
    source: str,
    data_type: str,
    raw_json: str,
    collected_at: str,
) -> None:
    """写入 raw_data 行；symbol 可空（用于板块/日历/新闻等"市场级"数据）。

    占位符策略：板块首页/热门板块/港美 IPO/新闻 写入时 symbol=None，
    避免污染 idx_raw_data_symbol_type 索引。
    """
    conn.execute(
        """INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at)
           VALUES (?, ?, ?, ?, ?)""",
        (symbol, source, data_type, raw_json, collected_at),
    )


class _CollectionHelpersMixin:
    """工具方法：run_logs 写入。"""

    @staticmethod
    def _write_run_log(
        conn: sqlite3.Connection,
        task_name: str,
        status: str,
        started_at: str,
        finished_at: str,
        error_message: str | None,
        affected_assets: int,
    ) -> None:
        conn.execute(
            """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                task_name,
                status,
                started_at,
                finished_at,
                error_message,
                affected_assets,
            ),
        )
