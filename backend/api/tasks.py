from fastapi import APIRouter, Depends, HTTPException, Query

from backend.scheduler.jobs import SchedulerManager, VALID_TASK_NAMES

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
_manager: SchedulerManager | None = None


def _set_scheduler(manager: SchedulerManager) -> None:
    """由 main.py lifespan 调用，注入调度器实例"""
    global _manager
    _manager = manager


def get_scheduler() -> SchedulerManager:
    """FastAPI Depends 依赖注入：返回调度器实例，未初始化时返回 503"""
    if _manager is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "SCHEDULER_NOT_READY", "detail": "调度器未初始化，请稍后重试"},
        )
    return _manager


# 向后兼容：main.py 仍可调用旧名称
set_scheduler = _set_scheduler


@router.get("/status")
def get_task_status(manager: SchedulerManager = Depends(get_scheduler)) -> dict:
    items: list[dict] = manager.get_task_status()
    return {"items": items}


@router.post("/trigger/{task_name}", status_code=202)
def trigger_task(
    task_name: str,
    manager: SchedulerManager = Depends(get_scheduler),
) -> dict:
    if task_name not in VALID_TASK_NAMES:
        raise HTTPException(status_code=404, detail={"error": "TASK_NOT_FOUND", "detail": f"任务 '{task_name}' 不存在"})
    success: bool = manager.trigger_task(task_name)
    if not success:
        raise HTTPException(status_code=500, detail={"error": "TRIGGER_FAILED", "detail": f"任务 '{task_name}' 触发失败"})
    return {"status": "triggered", "task_name": task_name}


@router.get("/logs")
def get_task_logs(
    task_name: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    manager: SchedulerManager = Depends(get_scheduler),
) -> dict:
    """查询任务运行日志。调度器不可用时回退到数据库直读。"""
    try:
        return manager.get_task_logs(task_name=task_name, status=status, page=page, page_size=page_size)
    except RuntimeError:
        from backend.storage.database import query_run_logs
        return query_run_logs(task_name=task_name, status=status, page=page, page_size=page_size)

