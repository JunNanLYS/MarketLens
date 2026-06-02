from fastapi import APIRouter, HTTPException, Query

from backend.scheduler.jobs import SchedulerManager, VALID_TASK_NAMES

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
    try:
        manager: SchedulerManager = _get_manager()
        return manager.get_task_logs(
            task_name=task_name, status=status, page=page, page_size=page_size
        )
    except RuntimeError:
        # Fallback: scheduler ???????? storage ????????? DB?
        from backend.storage.database import query_run_logs
        return query_run_logs(task_name=task_name, status=status, page=page, page_size=page_size)
