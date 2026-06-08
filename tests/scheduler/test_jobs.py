"""调度器模块测试 —— 验证异步化修复与基本契约。"""

import inspect
from contextlib import contextmanager
from unittest.mock import patch


def test_check_neo_data_token_on_startup_is_async() -> None:
    """`_check_neo_data_token_on_startup` 必须是 async def(否则阻塞 event loop)。

    修复:第 12 轮 bug #4 —— 原同步实现在 async lifespan 中直接调用,
    内部 `client.get_token_status()` 走 `TokenManager._read_cache()` 同步
    文件读,会阻塞 FastAPI 主事件循环。改为 async def + asyncio.to_thread
    包裹后,事件循环在文件 IO 期间可继续处理其他请求。
    """
    from backend.scheduler.jobs import _check_neo_data_token_on_startup

    assert inspect.iscoroutinefunction(_check_neo_data_token_on_startup), (
        "_check_neo_data_token_on_startup must be async def "
        "(avoid blocking event loop in async lifespan)"
    )


def test_scheduler_manager_start_is_async() -> None:
    """`SchedulerManager.start` 必须是 async def。

    修复:同上 —— 启动期需 await `_check_neo_data_token_on_startup` 与
    `asyncio.to_thread(_cleanup_naive_run_logs_once)`,因此 start 本体
    也必须改为 async def 以便在 lifespan 中 await 调用。
    """
    from backend.scheduler.jobs import SchedulerManager

    assert inspect.iscoroutinefunction(SchedulerManager.start), (
        "SchedulerManager.start must be async def"
    )


def test_neodata_health_log_writer_holds_write_lock(tmp_path, monkeypatch) -> None:
    """`_write_neo_health_log_sync` 写 run_logs 必须持 `_WRITE_LOCK`。

    修复:第 12 轮 bug #10 —— 原实现裸 `get_db()` 无锁,启动期单线程
    不会出错,但若未来扩展为周期任务,会与其他写路径竞争。
    防御性写法:现在就持锁。

    CI 复盘 (2026-06-08): 本测试曾因 dev venv 残留 db 状态而本地能跑、
    CI 干净 venv 跑挂 (`no such table: run_logs`)。已加 `tmp_path` 隔离
    + `set_db_path` 注入 + `init_db_sync` 显式建表,确保两端一致。
    """
    from backend.services import collection_service
    import backend.scheduler.jobs as jobs_mod
    from backend.storage.database import set_db_path
    from backend.storage.schema import init_db_sync

    # 隔离 db 路径 + 显式建表,避免依赖 dev venv 残留的 db 状态
    db_path = tmp_path / "test_jobs.db"
    monkeypatch.setattr("backend.storage.database._db_path_override", None)
    set_db_path(str(db_path))
    init_db_sync(str(db_path))

    observed_held: list[bool] = []

    @contextmanager
    def _fake_lock():
        # 记录进入时锁是否被持有; 真实 _WRITE_LOCK 单线程,这里只测是否被进入
        observed_held.append(True)
        yield

    # patch `get_db` 也 patch `_WRITE_LOCK` —— jobs.py 内是 `from
    # backend.services.collection_service import _WRITE_LOCK`,
    # news_service 的 import path 同理;需要同时 patch 三个位置
    with (
        patch.object(collection_service, "_WRITE_LOCK", new=_fake_lock()),
        patch.object(jobs_mod, "_WRITE_LOCK", new=_fake_lock()),
    ):
        # 直接调用 _write_neo_health_log_sync 验证持锁
        jobs_mod._write_neo_health_log_sync(
            task_name="neodata_health_test",
            status="success",
            started_at="2026-06-08T00:00:00+00:00",
            finished_at="2026-06-08T00:00:01+00:00",
            error_message=None,
            affected_assets=0,
        )

    assert observed_held, "_write_neo_health_log_sync 未进入 _WRITE_LOCK 上下文"
