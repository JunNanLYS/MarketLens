"""验证 scheduler/jobs.py::_check_neo_data_token_on_startup 三个分支。

该函数在应用启动时执行一次，核对 NeoData token 状态并写入 run_logs。
- 有 token    → success
- 无 token    → skipped
- 异常路径    → failure
- NeoData 禁用 → skipped
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.scheduler.jobs import _check_neo_data_token_on_startup
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


async def test_check_enabled_with_token_writes_success_log() -> None:
    """启用 NeoData 且有 token → run_logs 写入 success。"""
    with patch("backend.collectors.neodata_client.NeoDataClient") as MockClient:
        instance = MagicMock()
        instance.get_token_status.return_value = {
            "has_token": True,
            "source": "config",
            "expires_at": None,
        }
        MockClient.return_value = instance
        await _check_neo_data_token_on_startup()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'neodata_health'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["error_message"] is None


async def test_check_enabled_no_token_writes_skipped_log() -> None:
    """启用 NeoData 但无 token → run_logs 写入 skipped 并提示。"""
    with patch("backend.collectors.neodata_client.NeoDataClient") as MockClient:
        instance = MagicMock()
        instance.get_token_status.return_value = {
            "has_token": False,
            "source": "none",
            "expires_at": None,
        }
        MockClient.return_value = instance
        await _check_neo_data_token_on_startup()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'neodata_health'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert rows[0]["error_message"] is not None
    assert "token" in rows[0]["error_message"].lower()


async def test_check_disabled_writes_skipped_log() -> None:
    """NeoData 禁用 → run_logs 写入 skipped,不调用 NeoDataClient。"""
    with (
        patch("backend.scheduler.jobs.get_config") as mock_cfg,
        patch("backend.collectors.neodata_client.NeoDataClient") as MockClient,
    ):
        mock_cfg.return_value = {
            "data_sources": {
                "structured": [],
                "news": [
                    {"provider": "NeoDataProvider", "enabled": False},
                ],
            },
        }
        instance = MagicMock()
        instance.get_token_status.return_value = {
            "has_token": False,
            "source": "none",
            "expires_at": None,
        }
        MockClient.return_value = instance
        await _check_neo_data_token_on_startup()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'neodata_health'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    # 禁用时不应创建 NeoDataClient
    MockClient.assert_not_called()


async def test_check_exception_writes_failure_log() -> None:
    """检查过程中抛出异常 → run_logs 写入 failure, 不阻塞应用启动。"""
    with patch("backend.collectors.neodata_client.NeoDataClient") as MockClient:
        MockClient.side_effect = RuntimeError("unexpected boom")
        await _check_neo_data_token_on_startup()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'neodata_health'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "failure"
    assert rows[0]["error_message"] is not None
    assert "unexpected boom" in rows[0]["error_message"]
