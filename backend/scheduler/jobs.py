import asyncio
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from backend.config import get_config
from backend.services.collection_service import CollectionService
from backend.services.news_service import NewsService
from backend.services.report_service import ReportService
from backend.storage.database import get_db

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


def _run_cleanup() -> None:
    try:
        logger.info("定时任务触发: cleanup")
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM raw_data WHERE collected_at < datetime('now', '-30 days')"
            )
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("清理了 {} 条过期原始数据", deleted)
    except Exception:
        logger.exception("定时任务执行异常: cleanup")


_TASK_FUNCTIONS: dict[str, object] = {
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

    def start(self) -> None:
        """注册所有任务后启动调度器。"""
        self.register_jobs()
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
        from backend.storage.database import query_run_logs
        return query_run_logs(
            task_name=task_name, status=status, page=page, page_size=page_size,
        )



