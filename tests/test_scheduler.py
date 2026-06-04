import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.scheduler.jobs import SchedulerManager, VALID_TASK_NAMES
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


def _insert_run_log(
    task_name: str,
    status: str = "success",
    started_at: str | None = None,
    finished_at: str | None = None,
    error_message: str | None = None,
    affected_assets: int = 0,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                task_name,
                status,
                started_at or now,
                finished_at or now,
                error_message,
                affected_assets,
            ),
        )


class TestSchedulerManagerInit:

    def test_init_creates_scheduler(self) -> None:
        mgr = SchedulerManager()
        assert mgr._scheduler is not None

    def test_init_reads_timezone_from_config(self) -> None:
        mgr = SchedulerManager()
        assert str(mgr._scheduler.timezone) == "Asia/Shanghai"


class TestRegisterJobs:

    def test_register_jobs_adds_four_tasks(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        job_ids = [job.id for job in mgr._scheduler.get_jobs()]
        for name in VALID_TASK_NAMES:
            assert name in job_ids

    def test_register_jobs_quote_interval(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        job = mgr._scheduler.get_job("quote")
        assert job is not None

    def test_register_jobs_daily_close_cron(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        job = mgr._scheduler.get_job("daily_close")
        assert job is not None

    def test_register_jobs_news_interval(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        job = mgr._scheduler.get_job("news")
        assert job is not None

    def test_register_jobs_ai_report_cron(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        job = mgr._scheduler.get_job("ai_report")
        assert job is not None


class TestTriggerTask:

    def test_trigger_valid_task(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("quote")
        assert result is True

    def test_trigger_daily_close(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("daily_close")
        assert result is True

    def test_trigger_news(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("news")
        assert result is True

    def test_trigger_ai_report(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("ai_report")
        assert result is True

    def test_trigger_invalid_task(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("nonexistent")
        assert result is False

    def test_trigger_empty_name(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        result = mgr.trigger_task("")
        assert result is False


class TestGetTaskStatus:

    def test_get_task_status_no_logs(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        status = mgr.get_task_status()
        assert len(status) == 4
        for item in status:
            assert item["task_name"] in VALID_TASK_NAMES
            assert item["last_run_at"] is None
            assert item["last_status"] is None

    def test_get_task_status_with_logs(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        _insert_run_log(
            "quote",
            status="success",
            started_at=now,
            finished_at=now,
            affected_assets=10,
        )
        mgr = SchedulerManager()
        mgr.register_jobs()
        status = mgr.get_task_status()
        quote_status = next(s for s in status if s["task_name"] == "quote")
        assert quote_status["last_status"] == "success"
        assert quote_status["last_affected_assets"] == 10
        assert quote_status["last_error"] is None

    def test_get_task_status_with_failure_log(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        _insert_run_log(
            "news",
            status="failure",
            started_at=now,
            finished_at=now,
            error_message="连接超时",
            affected_assets=0,
        )
        mgr = SchedulerManager()
        mgr.register_jobs()
        status = mgr.get_task_status()
        news_status = next(s for s in status if s["task_name"] == "news")
        assert news_status["last_status"] == "failure"
        assert news_status["last_error"] == "连接超时"

    def test_get_task_status_duration_calculation(self) -> None:
        started = "2026-05-31T15:30:00+00:00"
        finished = "2026-05-31T15:30:05+00:00"
        _insert_run_log(
            "quote",
            status="success",
            started_at=started,
            finished_at=finished,
            affected_assets=5,
        )
        mgr = SchedulerManager()
        mgr.register_jobs()
        status = mgr.get_task_status()
        quote_status = next(s for s in status if s["task_name"] == "quote")
        assert quote_status["last_duration_ms"] == 5000

    def test_get_task_status_returns_description(self) -> None:
        mgr = SchedulerManager()
        mgr.register_jobs()
        status = mgr.get_task_status()
        for item in status:
            assert item["description"] is not None
            assert len(item["description"]) > 0
            assert item["schedule"] is not None


class TestTaskLogsAPI:

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_get_logs_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["page_info"]["total"] == 0

    def test_get_logs_with_data(self, client: TestClient) -> None:
        _insert_run_log("quote", status="success", affected_assets=5)
        _insert_run_log("news", status="failure", error_message="超时")
        resp = client.get("/api/v1/tasks/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_info"]["total"] == 2

    def test_get_logs_filter_by_task_name(self, client: TestClient) -> None:
        _insert_run_log("quote", status="success")
        _insert_run_log("news", status="success")
        resp = client.get("/api/v1/tasks/logs", params={"task_name": "quote"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_info"]["total"] == 1
        assert data["items"][0]["task_name"] == "quote"

    def test_get_logs_filter_by_status(self, client: TestClient) -> None:
        _insert_run_log("quote", status="success")
        _insert_run_log("news", status="failure", error_message="超时")
        resp = client.get("/api/v1/tasks/logs", params={"status": "failure"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_info"]["total"] == 1
        assert data["items"][0]["status"] == "failure"

    def test_get_logs_pagination(self, client: TestClient) -> None:
        for i in range(5):
            _insert_run_log("quote", status="success", affected_assets=i)
        resp = client.get("/api/v1/tasks/logs", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["page_info"]["total"] == 5
        assert data["page_info"]["total_pages"] == 3


class TestTaskStatusAPI:

    @pytest.fixture
    def client(self) -> None:
        from backend.api.tasks import set_scheduler

        mgr = SchedulerManager()
        mgr.register_jobs()
        set_scheduler(mgr)
        return TestClient(app)

    def test_get_status(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 4

    def test_get_status_with_logs(self, client: TestClient) -> None:
        now = datetime.now(timezone.utc).isoformat()
        _insert_run_log(
            "quote",
            status="success",
            started_at=now,
            finished_at=now,
            affected_assets=20,
        )
        resp = client.get("/api/v1/tasks/status")
        assert resp.status_code == 200
        data = resp.json()
        quote = next(i for i in data["items"] if i["task_name"] == "quote")
        assert quote["last_status"] == "success"
        assert quote["last_affected_assets"] == 20


class TestTriggerAPI:

    @pytest.fixture
    def client(self) -> None:
        from backend.api.tasks import set_scheduler

        mgr = SchedulerManager()
        mgr.register_jobs()
        set_scheduler(mgr)
        return TestClient(app)

    def test_trigger_valid_task(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/trigger/quote")
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_name"] == "quote"
        assert data["status"] == "triggered"

    def test_trigger_invalid_task(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/trigger/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "TASK_NOT_FOUND"

    def test_trigger_all_valid_tasks(self, client: TestClient) -> None:
        for name in VALID_TASK_NAMES:
            resp = client.post(f"/api/v1/tasks/trigger/{name}")
            assert resp.status_code == 202
            assert resp.json()["status"] == "triggered"
