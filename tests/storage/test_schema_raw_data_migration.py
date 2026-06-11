import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.storage.database import get_connection_sync
from backend.storage.schema import _migrate_raw_data_symbol_nullable_sync


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


def _create_raw_data_not_null_schema(conn: sqlite3.Connection) -> None:
    """构造迁移前的旧版 raw_data 表。"""
    conn.execute("DROP TABLE IF EXISTS raw_data")
    conn.execute(
        """
        CREATE TABLE raw_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            data_type TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            collected_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.commit()


def test_raw_data_migration_restores_foreign_keys_and_drops_not_null(
    db_path: str,
) -> None:
    """迁移完成后应恢复 FK，并让 symbol 变为可空。"""
    conn = get_connection_sync(db_path)
    try:
        _create_raw_data_not_null_schema(conn)
        conn.execute(
            "INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sh600519", "legacy", "quote", "{}", "2026-06-11T00:00:00+00:00"),
        )
        conn.commit()

        _migrate_raw_data_symbol_nullable_sync(conn)

        table_info = conn.execute("PRAGMA table_info(raw_data)").fetchall()
        symbol_row = next(row for row in table_info if row["name"] == "symbol")
        assert symbol_row["notnull"] == 0
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        backup_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_data__notnull_backup'"
        ).fetchone()
        assert backup_exists is None

        conn.execute(
            "INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (None, "legacy", "quote", "{}", "2026-06-11T00:01:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def test_raw_data_migration_rolls_back_and_restores_foreign_keys_on_failure(
    db_path: str,
) -> None:
    """迁移中途失败时应回滚并恢复 FK 开关。"""
    conn = get_connection_sync(db_path)

    class _FailingConnectionProxy:
        """代理 sqlite 连接，在指定 SQL 处注入失败。"""

        def __init__(self, real_conn: sqlite3.Connection) -> None:
            self._real_conn = real_conn
            self.statements: list[str] = []

        def execute(self, sql: str, parameters=()):
            self.statements.append(sql)
            if "INSERT INTO raw_data (id, symbol, source, data_type, raw_json, collected_at)" in sql:
                raise sqlite3.OperationalError("模拟迁移失败")
            return self._real_conn.execute(sql, parameters)

    try:
        _create_raw_data_not_null_schema(conn)
        proxy = _FailingConnectionProxy(conn)

        with pytest.raises(sqlite3.OperationalError, match="模拟迁移失败"):
            _migrate_raw_data_symbol_nullable_sync(proxy)  # type: ignore[arg-type]

        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        table_info = conn.execute("PRAGMA table_info(raw_data)").fetchall()
        symbol_row = next(row for row in table_info if row["name"] == "symbol")
        assert symbol_row["notnull"] == 1
        backup_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_data__notnull_backup'"
        ).fetchone()
        assert backup_exists is None
        assert any(sql == "ROLLBACK" for sql in proxy.statements)
    finally:
        conn.close()
