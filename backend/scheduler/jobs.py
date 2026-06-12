import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from backend.config import get_config
from backend.services.collection_service import CollectionService, _WRITE_LOCK
from backend.services.news_service import NewsService
from backend.services.report_service import ReportService
from backend.storage.database import get_connection_sync, get_db, query_run_logs


def _cleanup_naive_run_logs_once() -> None:
    """启动时一次性清理: run_logs 表中无 tz 标记的旧条目。

    历史上 jobs.py::_check_neo_data_token_on_startup 用过 naive datetime.now(),
    其他服务都用 timezone.utc。混合存储会让 get_task_status 计算 duration 时出错
    (naive - aware 抛 TypeError)。本函数只删缺 tz 标记的行(无 '+' 也无 'Z')。
    """
    try:
        with get_db() as conn:
            deleted: int = conn.execute(
                """
                DELETE FROM run_logs
                WHERE started_at IS NOT NULL
                  AND instr(started_at, '+') = 0
                  AND instr(started_at, 'Z') = 0
                  AND length(started_at) >= 10
                """
            ).rowcount
            if deleted > 0:
                logger.info("清理了 {} 条无 tz 标记的 run_logs 旧数据", deleted)
    except Exception:
        logger.exception("清理 naive run_logs 失败")


# NeoData 启动期健康检查：token 由外部 workbuddy 工具写入，
# 应用启动时核对一次，写入 run_logs。运行期间 token 过期不会被自动检测，
# 业务侧 NeoDataProvider 仍会按 optional=True 静默降级；如需运行期探测，
# 可在未来扩展为独立周期任务（参见 tasks 列表 "neodata_health" TODO 留口）。
_NEODATA_HEALTH_TASK_NAME = "neodata_health"


def _write_neo_health_log_sync(
    task_name: str,
    status: str,
    started_at: str,
    finished_at: str,
    error_message: str | None,
    affected_assets: int,
) -> None:
    """同步写 NeoData 健康检查 run_logs，持 _WRITE_LOCK 串行化。

    启动期单线程目前不会并发，但若未来扩展为周期任务（jobs.py 注释里
    已有 "neodata_health" TODO 留口），与其他写路径竞争时会要求 _WRITE_LOCK。
    现在就加上锁是防御性写法。
    """
    with _WRITE_LOCK:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO run_logs
                   (task_name, status, started_at, finished_at, error_message, affected_assets)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_name, status, started_at, finished_at, error_message, affected_assets),
            )


async def _check_neo_data_token_on_startup() -> None:
    """应用启动时检查 NeoData token 状态，写入 run_logs（异步版）。

    与原同步版本的差异:
    - 改为 async def，在 async lifespan 中可被 await
    - 文件 IO 通过 asyncio.to_thread 卸载,避免阻塞 event loop
      (TokenManager._read_cache 读 ~/.workbuddy/.neodata_token)

    - 有 token  → 记 success，UI 历史显示"OK"
    - 无 token  → 记 skipped，error_message 提示去 workbuddy 刷新
    - 异常      → 记 failure，不阻塞应用启动
    """
    started_at = datetime.now(timezone.utc).isoformat()
    status = "skipped"
    error_message: str | None = None
    affected_assets = 0
    try:
        from backend.collectors.neodata_client import NeoDataClient

        config = get_config()
        sources: list[dict] = list(
            config.get("data_sources", {}).get("structured", [])
        ) + list(config.get("data_sources", {}).get("news", []))
        neodata_cfg = next(
            (s for s in sources if s.get("provider") == "NeoDataProvider"),
            {},
        )
        if not neodata_cfg.get("enabled", True):
            status = "skipped"
            error_message = "NeoDataProvider 未启用"
        else:
            params = neodata_cfg.get("params") or {}
            client = NeoDataClient(
                endpoint=params.get(
                    "endpoint",
                    "https://copilot.tencent.com/agenttool/v1/neodata",
                ),
                config_token=params.get("token") or None,
                timeout=neodata_cfg.get("timeout", 30),
            )
            # 关键: 文件 IO 卸载线程池
            token_status = await asyncio.to_thread(client.get_token_status)
            if token_status.get("has_token"):
                status = "success"
                logger.info(
                    "NeoData token 就绪: source={}, expires_at={}",
                    token_status.get("source"),
                    token_status.get("expires_at"),
                )
            else:
                status = "skipped"
                error_message = (
                    "NeoData token 不可用,请到 workbuddy 工具刷新凭证 "
                    "(~/.workbuddy/.neodata_token)"
                )
                logger.warning(error_message)
    except Exception as e:
        status = "failure"
        error_message = f"NeoData 健康检查异常: {e}"
        logger.exception("NeoData 启动健康检查失败")

    finished_at = datetime.now(timezone.utc).isoformat()
    # 写 run_logs 改用 to_thread + WRITE_LOCK
    await asyncio.to_thread(
        _write_neo_health_log_sync,
        _NEODATA_HEALTH_TASK_NAME,
        status,
        started_at,
        finished_at,
        error_message,
        affected_assets,
    )


TASK_DESCRIPTIONS: dict[str, str] = {
    "quote": "实时行情采集",
    "daily_close": "日收盘数据采集",
    "news": "新闻采集",
    "ai_report": "AI 分析报告",
    "cleanup": "过期数据清理",
}

TASK_SCHEDULE_DESCRIPTIONS: dict[str, str] = {
    "quote": "每 15 分钟",
    "daily_close": "交易日 16:00",
    "news": "每 60 分钟",
    "ai_report": "每日 20:00",
    "cleanup": "每日 3:30",
}

VALID_TASK_NAMES: set[str] = {"quote", "daily_close", "news", "ai_report", "cleanup"}


# 模块级懒加载单例，避免每个 tick 重建 Service 实例和内部 httpx 客户端。
# 每次 tick 仍以 asyncio.run() 创建独立事件循环，确保不会与 FastAPI 主线程
# 的事件循环发生冲突（仅复用 Service 对象本身，不复用 loop/connection）。
_collection_service: CollectionService | None = None
_news_service: NewsService | None = None


def _get_collection_service() -> CollectionService:
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service


def _get_news_service() -> NewsService:
    global _news_service
    if _news_service is None:
        _news_service = NewsService()
    return _news_service


def _run_quote() -> None:
    try:
        logger.info("定时任务触发: quote")
        asyncio.run(_get_collection_service().collect_quotes())
    except Exception:
        logger.exception("定时任务执行异常: quote")


def _run_daily_close() -> None:
    try:
        logger.info("定时任务触发: daily_close")
        asyncio.run(_get_collection_service().collect_daily_close())
    except Exception:
        logger.exception("定时任务执行异常: daily_close")


def _run_news() -> None:
    try:
        logger.info("定时任务触发: news")
        asyncio.run(_get_news_service().collect_news())
    except Exception:
        logger.exception("定时任务执行异常: news")


def _run_ai_report() -> None:
    try:
        logger.info("定时任务触发: ai_report")
        asyncio.run(ReportService.generate_reports())
    except Exception:
        logger.exception("定时任务执行异常: ai_report")


# 过期数据清理注册表：表名 → (时间列名, 保留天数)
# 时间列名语义：
#   - collected_at: 采集时间戳，按"采集时间"滚动保留（适合 etf_basic/etf_holdings/us_financials
#     等因 UNIQUE(code/symbol, date, source) 每日 upsert 的表，保留 N 天采集快照即可）
#   - date / report_date / event_date / end_date: 数据所属业务日期，按"业务日期"滚动保留
#     （适合按日增量写入的行情/榜单/事件类表）
# 保留天数原则：
#   - 行情/榜单/事件类（每日增量、价值随时间衰减）：365 天
#   - 财报/净值/历史/大单/龙虎榜（业务分析价值高）：1825 天（5 年）
# 调整策略：仅修改本字典即可，无需改清理逻辑。
CLEANUP_RULES: dict[str, tuple[str, int]] = {
    "raw_data": ("collected_at", 30),
    "news_items": ("collected_at", 90),  # 用 collected_at 而非 published_at：避免历史新闻同步时 published_at 太老被立刻清掉
    "etf_basic": ("collected_at", 365),
    "etf_holdings": ("collected_at", 365),
    "etf_nav_history": ("date", 1825),
    "etf_holders": ("report_date", 365),  # 表内业务日期列名为 report_date，非 date
    "etf_financial": ("date", 1825),
    "sector_daily_quote": ("date", 365),
    "us_financials": ("collected_at", 1825),
    "ipo_exdiv_calendar": ("event_date", 1825),
    "chip_distribution": ("date", 365),
    "margintrade_data": ("date", 365),
    "blocktrade_data": ("date", 1825),
    "lhb_data": ("date", 1825),
    "profit_forecasts": ("report_period", 1825),
}


def _run_cleanup() -> None:
    """按 CLEANUP_RULES 注册表清理 13 张新表 + raw_data 的过期数据。

    策略：
      - 注册表驱动：新增/调整保留策略仅需改 CLEANUP_RULES
      - 单表失败不影响其他表（每个 DELETE 独立 try/except）
      - 时间列名/保留天数均通过参数化绑定传入，避免 SQL 注入
      - 表名/列名取自模块级常量 CLEANUP_RULES，安全
    """
    try:
        logger.info("定时任务触发: cleanup")
        total_deleted: int = 0
        with _WRITE_LOCK:
            conn = get_connection_sync()
            try:
                for table, (time_col, days) in CLEANUP_RULES.items():
                    try:
                        cursor = conn.execute(
                            f"DELETE FROM {table} "  # 表名来自模块级常量，安全
                            f"WHERE {time_col} < datetime('now', ?)",  # 同上
                            (f"-{days} days",),
                        )
                        deleted: int = cursor.rowcount
                        total_deleted += deleted
                        if deleted > 0:
                            logger.info(
                                "清理了 {} 条 {} 过期数据 ({}>{}天)",
                                deleted,
                                table,
                                time_col,
                                days,
                            )
                    except Exception:
                        # 单表失败不影响其他表：cleanup 是幂等可重入的
                        logger.exception("清理表 {} 失败", table)
                conn.commit()
            finally:
                conn.close()
        if total_deleted > 0:
            logger.info("cleanup 本次共清理 {} 条过期数据", total_deleted)
    except Exception:
        logger.exception("定时任务执行异常: cleanup")


_TASK_FUNCTIONS: dict[str, Callable[[], None]] = {
    "quote": _run_quote,
    "daily_close": _run_daily_close,
    "news": _run_news,
    "ai_report": _run_ai_report,
    "cleanup": _run_cleanup,
}


class SchedulerManager:
    """APScheduler 调度器管理器：注册并管理所有后台定时任务。"""

    def __init__(self) -> None:
        """读取 scheduler 配置节并初始化后台调度器实例。"""
        config = get_config()
        scheduler_cfg: dict = config.get("scheduler", {})
        tz: str = scheduler_cfg.get("timezone", "Asia/Shanghai")
        self._scheduler = BackgroundScheduler(timezone=tz)
        self._tasks_cfg: dict = scheduler_cfg.get("tasks", {})

    def register_jobs(self) -> None:
        """从配置注册 quote / daily_close / news / ai_report / cleanup 等所有定时任务。"""
        quote_cfg: dict = self._tasks_cfg.get("quote", {})
        quote_interval: int = quote_cfg.get("interval", 15)
        self._scheduler.add_job(
            _run_quote,
            trigger=IntervalTrigger(minutes=quote_interval),
            id="quote",
            name=TASK_DESCRIPTIONS["quote"],
            replace_existing=True,
        )

        daily_close_cfg: dict = self._tasks_cfg.get("daily_close", {})
        daily_close_cron: str = daily_close_cfg.get("cron", "0 16 * * 1-5")
        self._scheduler.add_job(
            _run_daily_close,
            trigger=CronTrigger.from_crontab(daily_close_cron),
            id="daily_close",
            name=TASK_DESCRIPTIONS["daily_close"],
            replace_existing=True,
        )

        news_cfg: dict = self._tasks_cfg.get("news", {})
        news_interval: int = news_cfg.get("interval", 60)
        self._scheduler.add_job(
            _run_news,
            trigger=IntervalTrigger(minutes=news_interval),
            id="news",
            name=TASK_DESCRIPTIONS["news"],
            replace_existing=True,
        )

        ai_report_cfg: dict = self._tasks_cfg.get("ai_report", {})
        ai_report_cron: str = ai_report_cfg.get("cron", "0 20 * * *")
        self._scheduler.add_job(
            _run_ai_report,
            trigger=CronTrigger.from_crontab(ai_report_cron),
            id="ai_report",
            name=TASK_DESCRIPTIONS["ai_report"],
            replace_existing=True,
        )

        cleanup_cfg: dict = self._tasks_cfg.get("cleanup", {})
        cleanup_cron: str = cleanup_cfg.get("cron", "30 3 * * *")
        self._scheduler.add_job(
            _run_cleanup,
            trigger=CronTrigger.from_crontab(cleanup_cron),
            id="cleanup",
            name=TASK_DESCRIPTIONS["cleanup"],
            replace_existing=True,
        )

        logger.info("已注册 {} 个定时任务", len(VALID_TASK_NAMES))

    def _get_schedule_description(self, task_name: str) -> str:
        cfg = self._tasks_cfg.get(task_name, {})
        if "interval" in cfg:
            return f"每 {cfg['interval']} 分钟"
        if "cron" in cfg:
            parts = cfg["cron"].split()
            if len(parts) == 5:
                minute = parts[0]
                hour = parts[1]
                day_of_week = parts[4]
                if minute == "0":
                    time_str = f"{hour}:00"
                else:
                    time_str = f"{hour}:{minute.zfill(2)}"
                if day_of_week == "1-5":
                    return f"交易日 {time_str}"
                return f"每日 {time_str}"
            return f"CRON: {cfg['cron']}"
        return TASK_SCHEDULE_DESCRIPTIONS.get(task_name, "")

    async def start(self) -> None:
        """注册所有任务后启动调度器（异步版）。

        启动期做 3 件事:
        1. register_jobs() - 注册 5 个 cron/interval 任务
        2. 一次性清理 run_logs 中无 tz 标记的旧数据
        3. 一次性 NeoData token 健康检查

        步骤 2/3 都涉及文件 IO,通过 asyncio.to_thread 卸载,避免
        阻塞 FastAPI 主事件循环（CLAUDE.md 硬约束）。
        """
        self.register_jobs()
        # 启动时清理: run_logs 表中无 tz 标记的旧数据(一次性)。
        # 文件 IO 卸载线程池,避免阻塞 event loop
        await asyncio.to_thread(_cleanup_naive_run_logs_once)
        # 启动时一次性健康检查：NeoData token 由外部 workbuddy 工具管理,
        # 应用启动核对一次,结果写 run_logs 供 UI 历史查询。
        # 运行期 token 失效由业务侧 NeoDataProvider 静默降级兜底。
        await _check_neo_data_token_on_startup()
        self._scheduler.start()
        logger.info("调度器已启动")

    def shutdown(self) -> None:
        """关闭调度器，不再等待正在执行的任务。"""
        self._scheduler.shutdown(wait=False)
        logger.info("调度器已关闭")

    def trigger_task(self, task_name: str) -> bool:
        """手动触发指定名称的定时任务。

        Args:
            task_name: 任务名，可选 quote / daily_close / news / ai_report / cleanup。

        Returns:
            触发成功返回 True；任务名无效或执行失败返回 False。
        """
        if task_name not in VALID_TASK_NAMES:
            logger.warning("无效的任务名: {}", task_name)
            return False
        func = _TASK_FUNCTIONS[task_name]
        try:
            func()
        except Exception:
            logger.exception("手动触发任务失败: {}", task_name)
            return False
        logger.info("已手动触发任务: {}", task_name)
        return True

    def get_task_status(self) -> list[dict]:
        """汇总每个任务最近一次执行情况与下一次执行时间。

        Returns:
            每个任务一条记录，包含描述、调度表达式、最近运行状态、耗时、错误、下次运行时间等。
        """
        result: list[dict] = []
        task_names: list[str] = sorted(VALID_TASK_NAMES)
        placeholders = ",".join(["?"] * len(task_names))
        with get_db() as conn:
            rows = conn.execute(
                f"""SELECT task_name, status, started_at, finished_at,
                           error_message, affected_assets
                    FROM (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY task_name ORDER BY started_at DESC
                        ) as rn
                        FROM run_logs
                        WHERE task_name IN ({placeholders})
                    ) WHERE rn = 1""",
                task_names,
            ).fetchall()
            latest_rows: dict[str, object] = {row["task_name"]: row for row in rows}

            for task_name in VALID_TASK_NAMES:
                row = latest_rows.get(task_name)

                last_run_at: str | None = None
                last_status: str | None = None
                last_duration_ms: int | None = None
                last_affected_assets: int | None = None
                last_error: str | None = None

                if row is not None:
                    last_run_at = row["started_at"]
                    last_status = row["status"]
                    last_affected_assets = row["affected_assets"]
                    last_error = row["error_message"]
                    if row["started_at"] and row["finished_at"]:
                        try:
                            started = datetime.fromisoformat(row["started_at"])
                            finished = datetime.fromisoformat(row["finished_at"])
                            last_duration_ms = int(
                                (finished - started).total_seconds() * 1000
                            )
                        except (ValueError, TypeError):
                            last_duration_ms = None

                next_run_at: str | None = None
                job = self._scheduler.get_job(task_name)
                if job is not None:
                    try:
                        nrt = job.next_run_time
                        if nrt is not None:
                            next_run_at = nrt.isoformat()
                    except AttributeError:
                        next_run_at = None

                result.append(
                    {
                        "task_name": task_name,
                        "description": TASK_DESCRIPTIONS[task_name],
                        "schedule": self._get_schedule_description(task_name),
                        "last_run_at": last_run_at,
                        "last_status": last_status,
                        "last_duration_ms": last_duration_ms,
                        "last_affected_assets": last_affected_assets,
                        "last_error": last_error,
                        "next_run_at": next_run_at,
                    }
                )
        return result

    def get_task_logs(
        self,
        task_name: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询任务运行日志，委托 database.query_run_logs 实现。

        Args:
            task_name: 按任务名过滤
            status: 按状态过滤（success / failure）
            page: 页码
            page_size: 每页数量

        Returns:
            含 items 和 page_info 的字典
        """
        return query_run_logs(
            task_name=task_name,
            status=status,
            page=page,
            page_size=page_size,
        )
