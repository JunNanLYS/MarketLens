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
from backend.api.tasks import set_scheduler
from backend.config import get_config
from backend.scheduler.jobs import SchedulerManager
from backend.storage.schema import init_db

_scheduler_manager: SchedulerManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_manager
    logger.info("MarketLens 应用启动中...")
    init_db()
    logger.info("数据库初始化完成")
    _scheduler_manager = SchedulerManager()
    _scheduler_manager.start()
    set_scheduler(_scheduler_manager)
    logger.info("MarketLens 应用已启动")
    yield
    if _scheduler_manager is not None:
        _scheduler_manager.shutdown()
    logger.info("MarketLens 应用已关闭")


app = FastAPI(
    title="MarketLens API",
    version="0.1.0",
    lifespan=lifespan,
)

config = get_config()
cors_origins = config.get("security", {}).get("cors_origins", ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "title": app.title,
        "version": app.version,
        "docs_url": "/docs",
    }
