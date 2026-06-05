"""验证 FastAPI lifespan 正确 await init_db(), 表被实际创建。

回归 f098226 修复 —— 之前 main.py 的 lifespan 漏掉 await init_db()，
导致表不会被创建，/_check_neo_data_token_on_startup 在启动期崩溃。
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.storage.database import get_connection_sync, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch) -> str:
    """为每个测试提供独立临时数据库。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    monkeypatch.setattr(
        "backend.storage.database._db_path_override", path,
    )
    yield path
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


def test_init_db_creates_tables(isolated_db: str) -> None:
    """f098226 修复回归测试: lifespan 启动后所有表必须已建。"""
    with TestClient(app) as client:
        conn = get_connection_sync()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r["name"] for r in rows}
        finally:
            conn.close()
        assert "market_quotes" in table_names, "lifespan 未 await init_db() 或表未创建"
        assert "tracked_assets" in table_names
        assert "run_logs" in table_names
        assert "ai_reports" in table_names
        # health 端点应正常返回（不抛异常）
        resp = client.get("/api/v1/health")
        assert resp.status_code in (200, 503)
        body: dict = resp.json()
        assert "database" in body
