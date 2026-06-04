from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from backend.api.assets import router as assets_router
from backend.api.data import router as data_router
from backend.api.neodata import router as neodata_router
from backend.api.news import router as news_router
from backend.api.portfolio import router as portfolio_router
from backend.api.reports import router as reports_router
from backend.api.tasks import router as tasks_router
from backend.api.tasks import _set_scheduler
from backend.config import get_config
from backend.scheduler.jobs import SchedulerManager
from backend.storage.schema import init_db

_scheduler_manager: SchedulerManager | None = None
_db_ready = False
_scheduler_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_manager, _db_ready, _scheduler_ready
    logger.info("MarketLens 应用启动中...")
    try:
        init_db()
        _db_ready = True
        logger.info("数据库初始化完成")
    except Exception:
        logger.exception("数据库初始化失败")
    try:
        _scheduler_manager = SchedulerManager()
        _scheduler_manager.start()
        _scheduler_ready = True
        _set_scheduler(_scheduler_manager)
        logger.info("MarketLens 应用已启动")
    except Exception:
        logger.exception("调度器启动失败")
    yield
    if _scheduler_manager is not None:
        _scheduler_manager.shutdown()
    logger.info("MarketLens 应用已关闭")


app = FastAPI(
    title="MarketLens API",
    description="MarketLens 是一个本地优先、证据驱动的 AI 金融研究助手 API。",
    version="0.1.0",
    lifespan=lifespan,
)

config = get_config()
# CORS 配置：默认仅放行本地 Streamlit (8501)，如需放行其他来源请在 config.yaml 的
# security.cors_origins 中显式声明，避免在生产环境中使用通配符。
_default_cors_origins = ["http://localhost:8501", "http://127.0.0.1:8501"]
_default_cors_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
_default_cors_headers = ["Content-Type", "Authorization", "X-API-Key"]

cors_origins = config.get("security", {}).get("cors_origins", _default_cors_origins)
cors_methods = config.get("security", {}).get("cors_methods", _default_cors_methods)
cors_headers = config.get("security", {}).get("cors_headers", _default_cors_headers)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

app.include_router(assets_router)
app.include_router(data_router)
app.include_router(neodata_router)
app.include_router(news_router)
app.include_router(reports_router)
app.include_router(portfolio_router)
app.include_router(tasks_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        content = exc.detail
    else:
        content = {"error": "REQUEST_ERROR", "detail": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: {} {}", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "detail": "内部服务错误"},
    )


@app.get("/api/v1/health")
def health_check() -> dict:
    return {
        "status": "ok" if (_db_ready and _scheduler_ready) else "degraded",
        "database": "ok" if _db_ready else "error",
        "scheduler": "ok" if _scheduler_ready else "error",
    }


@app.get("/")
def root() -> dict:
    return {
        "title": app.title,
        "version": app.version,
        "docs_url": "/docs",
    }
