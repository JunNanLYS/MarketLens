"""验证 _run_* 包装函数写入 run_logs。"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from backend.storage.database import aget_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db(path)
    try:
        yield
    finally:
        set_db_path(None)
        Path(path).unlink(missing_ok=True)


class TestRunFunctionsWriteRunLogs:
    """验证 _run_* 包装函数调用子服务后 run_logs 持久化。"""

    @patch("backend.collectors.create_providers", return_value={"structured": [], "news": []})
    @patch("backend.services.collection_service.CollectionService")
    async def test_run_quote_writes_run_log(
        self, mock_svc_cls: MagicMock, mock_create: MagicMock
    ) -> None:
        """调用 _run_quote 后 run_logs 表中应有 quote 记录。"""
        from backend.scheduler.jobs import _run_quote

        mock_instance = MagicMock()
        async def _fake_collect():
            async with aget_db() as conn:
                now = datetime.now(timezone.utc).isoformat()
                await conn.execute(
                    "INSERT INTO run_logs (task_name, status, started_at, finished_at, affected_assets) VALUES (?, ?, ?, ?, ?)",
                    ("quote", "success", now, now, 3),
                )
        mock_instance.collect_quotes = _fake_collect
        mock_svc_cls.return_value = mock_instance

        await _run_quote()

        async with aget_db() as conn:
            cursor = await conn.execute(
                "SELECT * FROM run_logs WHERE task_name = 'quote' ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()

        assert row is not None, "run_logs 中应有 quote 记录"
        assert row["task_name"] == "quote"
        assert row["status"] == "success"
        assert row["started_at"] is not None
        assert row["finished_at"] is not None

    @patch("backend.collectors.create_providers", return_value={"structured": [], "news": []})
    @patch("backend.services.news_service.NewsService")
    async def test_run_news_writes_run_log(
        self, mock_svc_cls: MagicMock, mock_create: MagicMock
    ) -> None:
        """调用 _run_news 后 run_logs 表中应有 news 记录。"""
        from backend.scheduler.jobs import _run_news

        mock_instance = MagicMock()
        async def _fake_collect():
            async with aget_db() as conn:
                now = datetime.now(timezone.utc).isoformat()
                await conn.execute(
                    "INSERT INTO run_logs (task_name, status, started_at, finished_at, affected_assets) VALUES (?, ?, ?, ?, ?)",
                    ("news", "success", now, now, 5),
                )
            return {"collected": 0, "skipped": 0}
        mock_instance.collect_news = _fake_collect
        mock_svc_cls.return_value = mock_instance

        await _run_news()

        async with aget_db() as conn:
            cursor = await conn.execute(
                "SELECT * FROM run_logs WHERE task_name = 'news' ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()

        assert row is not None, "run_logs 中应有 news 记录"
        assert row["task_name"] == "news"
        assert row["status"] == "success"
        assert row["started_at"] is not None
        assert row["finished_at"] is not None
