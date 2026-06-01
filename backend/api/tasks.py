from fastapi import APIRouter, HTTPException, Query

from backend.scheduler.jobs import SchedulerManager, VALID_TASK_NAMES
from backend.storage.database import get_db

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

_manager: SchedulerManager | None = None


def set_scheduler(manager: SchedulerManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> SchedulerManager:
    if _manager is None:
        raise RuntimeError("调度器管理器未初始化")
    return _manager


@router.get("/status")
def get_task_status() -> dict:
    manager: SchedulerManager = _get_manager()
    items: list[dict] = manager.get_task_status()
    return {"items": items}


@router.post("/trigger/{task_name}", status_code=202)
def trigger_task(task_name: str) -> dict:
    if task_name not in VALID_TASK_NAMES:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND", "detail": f"任务 '{task_name}' 不存在"},
        )
    manager: SchedulerManager = _get_manager()
    success: bool = manager.trigger_task(task_name)
    if not success:
        raise HTTPException(
            status_code=500,
            detail={"error": "TRIGGER_FAILED", "detail": f"任务 '{task_name}' 触发失败"},
        )
    return {"status": "triggered", "task_name": task_name}


@router.get("/logs")
def get_task_logs(
    task_name: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    conditions: list[str] = []
    params: list[str | int] = []
    if task_name is not None:
        conditions.append("task_name = ?")
        params.append(task_name)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    where_clause: str = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

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
