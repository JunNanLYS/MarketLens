from datetime import datetime, timezone

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
}

TASK_SCHEDULE_DESCRIPTIONS: dict[str, str] = {
    "quote": "每 15 分钟",
    "daily_close": "交易日 16:00",
    "news": "每 60 分钟",
    "ai_report": "每日 20:00",
}

VALID_TASK_NAMES: set[str] = {"quote", "daily_close", "news", "ai_report"}


def _run_quote() -> None:
    try:
        logger.info("定时任务触发: quote")
        CollectionService().collect_quotes()
    except Exception:
        logger.exception("定时任务执行异常: quote")


def _run_daily_close() -> None:
    try:
        logger.info("定时任务触发: daily_close")
        CollectionService().collect_daily_close()
    except Exception:
        logger.exception("定时任务执行异常: daily_close")


def _run_news() -> None:
    try:
        logger.info("定时任务触发: news")
        NewsService().collect_news()
    except Exception:
        logger.exception("定时任务执行异常: news")


def _run_ai_report() -> None:
    try:
        logger.info("定时任务触发: ai_report")
        ReportService.generate_reports()
    except Exception:
        logger.exception("定时任务执行异常: ai_report")


_TASK_FUNCTIONS: dict[str, object] = {
    "quote": _run_quote,
    "daily_close": _run_daily_close,
    "news": _run_news,
    "ai_report": _run_ai_report,
}


class SchedulerManager:

    def __init__(self) -> None:
        config = get_config()
        scheduler_cfg: dict = config.get("scheduler", {})
        tz: str = scheduler_cfg.get("timezone", "Asia/Shanghai")
        self._scheduler = BackgroundScheduler(timezone=tz)
        self._tasks_cfg: dict = scheduler_cfg.get("tasks", {})

    def register_jobs(self) -> None:
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

        logger.info("已注册 {} 个定时任务", len(VALID_TASK_NAMES))

    def start(self) -> None:
        self.register_jobs()
        self._scheduler.start()
        logger.info("调度器已启动")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("调度器已关闭")

    def trigger_task(self, task_name: str) -> bool:
        if task_name not in VALID_TASK_NAMES:
            logger.warning("无效的任务名: {}", task_name)
            return False
        func = _TASK_FUNCTIONS[task_name]
        self._scheduler.add_job(
            func,
            id=f"{task_name}_manual_{datetime.now(timezone.utc).timestamp()}",
            name=f"手动触发: {TASK_DESCRIPTIONS[task_name]}",
        )
        logger.info("已手动触发任务: {}", task_name)
        return True

    def get_task_status(self) -> list[dict]:
        result: list[dict] = []
        with get_db() as conn:
            for task_name in VALID_TASK_NAMES:
                row = conn.execute(
                    """SELECT task_name, status, started_at, finished_at,
                              error_message, affected_assets
                       FROM run_logs
                       WHERE task_name = ?
                       ORDER BY started_at DESC LIMIT 1""",
                    (task_name,),
                ).fetchone()

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
                        "schedule": TASK_SCHEDULE_DESCRIPTIONS[task_name],
                        "last_run_at": last_run_at,
                        "last_status": last_status,
                        "last_duration_ms": last_duration_ms,
                        "last_affected_assets": last_affected_assets,
                        "last_error": last_error,
                        "next_run_at": next_run_at,
                    }
                )
        return result
