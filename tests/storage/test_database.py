import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.storage.database import get_connection, get_db
from backend.storage.schema import init_db


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    yield path
    Path(path).unlink(missing_ok=True)


def test_get_connection(db_path: str) -> None:
    conn = get_connection(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_pragma_journal_mode(db_path: str) -> None:
    conn = get_connection(db_path)
    result = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert result == "wal"
    conn.close()


def test_pragma_foreign_keys(db_path: str) -> None:
    conn = get_connection(db_path)
    result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert result == 1
    conn.close()


def test_get_db_commit(db_path: str) -> None:
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


def test_get_db_rollback(db_path: str) -> None:
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


def test_get_db_auto_close(db_path: str) -> None:
    with get_db(db_path) as conn:
        assert conn.total_changes >= 0
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
