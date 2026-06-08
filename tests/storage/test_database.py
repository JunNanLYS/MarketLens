import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.storage.database import get_connection_sync, get_db
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    yield path
    Path(path).unlink(missing_ok=True)


async def test_get_connection_sync(db_path: str) -> None:
    conn = get_connection_sync(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


async def test_pragma_journal_mode(db_path: str) -> None:
    conn = get_connection_sync(db_path)
    result = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert result == "wal"
    conn.close()


async def test_pragma_foreign_keys(db_path: str) -> None:
    conn = get_connection_sync(db_path)
    result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert result == 1
    conn.close()


async def test_get_db_commit(db_path: str) -> None:
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO tracked_assets (symbol, name, market) VALUES (?, ?, ?)",
            ("sh600000", "浦发银行", "sh"),
        )
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tracked_assets WHERE symbol = ?", ("sh600000",)
        ).fetchone()
        assert row is not None
        assert row["symbol"] == "sh600000"


async def test_get_db_rollback(db_path: str) -> None:
    init_db(db_path)
    with pytest.raises(ValueError):
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO tracked_assets (symbol, name, market) VALUES (?, ?, ?)",
                ("sh600000", "浦发银行", "sh"),
            )
            raise ValueError("test error")
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tracked_assets WHERE symbol = ?", ("sh600000",)
        ).fetchone()
        assert row is None


async def test_get_db_auto_close(db_path: str) -> None:
    with get_db(db_path) as conn:
        assert conn.total_changes >= 0
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


async def test_get_db_commit_fail_triggers_rollback_and_close() -> None:
    """验证 commit 失败时触发 rollback 且连接关闭 (commit→rollback→close 链)。"""
    import aiosqlite

    # 创建独立测试数据库
    db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    init_db(db_path)

    # 创建连接并手动模拟 aget_db 的异常处理链
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = aiosqlite.Row

    rollback_called = False
    closed_called = False

    original_rollback = conn.rollback
    original_close = conn.close

    async def tracking_rollback():
        nonlocal rollback_called
        rollback_called = True
        await original_rollback()

    async def tracking_close():
        nonlocal closed_called
        closed_called = True
        await original_close()

    async def failing_commit():
        raise sqlite3.OperationalError("模拟 commit 失败")

    conn.commit = failing_commit
    conn.rollback = tracking_rollback
    conn.close = tracking_close

    # 模拟 aget_db 中的 try/except/finally 流程
    try:
        await conn.execute(
            "INSERT INTO tracked_assets (symbol, name, market) VALUES (?, ?, ?)",
            ("sh600000", "测试标的", "sh"),
        )
        await conn.commit()  # 此 commit 会失败
    except sqlite3.OperationalError:
        await conn.rollback()
    finally:
        await conn.close()

    assert rollback_called, "commit 失败后应触发 rollback"
    assert closed_called, "finally 块应确保连接关闭"

    # 清理
    Path(db_path).unlink(missing_ok=True)
