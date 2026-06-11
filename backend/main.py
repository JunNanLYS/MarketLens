import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from backend.api.assets import router as assets_router
from backend.api.data import router as data_router
from backend.api.data_sources import router as data_sources_router
from backend.api.neodata import router as neodata_router
from backend.api.news import router as news_router
from backend.api.portfolio import router as portfolio_router
from backend.api.reports import router as reports_router
from backend.api.tasks import router as tasks_router
from backend.api.tasks import _set_scheduler
from backend.config import get_config
from backend.scheduler.jobs import SchedulerManager
from backend.storage.schema import init_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """注入常用安全响应头，抑制 XSS/点击劫持/MIME 嗅探/信息泄露。

    - X-Content-Type-Options: nosniff — 禁止浏览器进行 MIME 嗅探。
    - X-Frame-Options: DENY — 禁止任何 iframe 嵌入。
    - Referrer-Policy: no-referrer — 出口链路不携带来源。
    - Strict-Transport-Security: 强制 HTTPS（本地开发无影响，生产环境必须 HTTPS）。
    - Content-Security-Policy: 保持宽松（FastAPI Swagger UI 需要 inline script/style）。
    """

    async def dispatch(self, request: StarletteRequest, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        # CSP 留宽松：Swagger UI 需要 inline script/style
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'"
        )
        return response


_scheduler_manager: SchedulerManager | None = None
_db_ready = False
_scheduler_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_manager, _db_ready, _scheduler_ready
    logger.info("MarketLens 应用启动中...")
    try:
        await init_db()
        _db_ready = True
        logger.info("数据库初始化完成")
    except Exception:
        logger.exception("数据库初始化失败")
    try:
        _scheduler_manager = SchedulerManager()
        await _scheduler_manager.start()
        _scheduler_ready = True
        _set_scheduler(_scheduler_manager)
        logger.info("MarketLens 应用已启动")
    except Exception:
        logger.exception("调度器启动失败")
    yield
    if _scheduler_manager is not None:
        _scheduler_manager.shutdown()
    # 关闭所有 Provider 持有的 httpx.AsyncClient，避免 Windows Proactor 偶发
    # "Unclosed client" 警告及进程被强制 kill 时的 socket 泄漏。详见 CLAUDE.md
    # "Resource cleanup" 硬约束。Service 持有 list[BaseProvider]，遍历调
    # close()；BaseProvider.close() 是空默认实现（base.py:43,92），无 httpx 客户端
    # 的 Provider 走空操作，有客户端的子类会覆盖 aclose()。单 Provider 失败
    # 不阻断其他 Provider 的关闭。
    from backend.scheduler.jobs import _get_collection_service, _get_news_service

    try:
        for provider in _get_collection_service()._get_structured_providers():
            try:
                await provider.close()
            except Exception:
                logger.exception("关闭 Provider 失败: {}", provider.name)
        for provider in _get_news_service()._providers:
            try:
                await provider.close()
            except Exception:
                logger.exception("关闭 Provider 失败: {}", provider.name)
    except Exception:
        logger.exception("Provider 关闭阶段异常")
    logger.info("MarketLens 应用已关闭")


app = FastAPI(
    title="MarketLens API",
    description="MarketLens 是一个本地优先、证据驱动的 AI 金融研究助手 API。",
    version="0.1.0",
    lifespan=lifespan,
)

config = get_config()
# CORS 配置：默认放行本地前端（5173 = Vite dev, 8000 = 生产模式挂载），
# 如需放行其他来源请在 config.yaml 的
# security.cors_origins 中显式声明，避免在生产环境中使用通配符。
_default_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_default_cors_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
_default_cors_headers = ["Content-Type", "Authorization", "X-API-Key"]

cors_origins = config.get("security", {}).get("cors_origins", _default_cors_origins)
cors_methods = config.get("security", {}).get("cors_methods", _default_cors_methods)
cors_headers = config.get("security", {}).get("cors_headers", _default_cors_headers)

# 启动日志：打印生效的 CORS 配置,便于运维核对（CLAUDE.md 项目特性允许 *，
# 但生产部署若误带配置上线可快速发现。CORS 日志只打 origins，不打 methods/headers）
logger.info("CORS allowed origins: {}", cors_origins)

# 安全头中间件必须在 CORS 之前注册，
# 以保证 preflight 401/4xx 响应也携带安全头。
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

app.include_router(assets_router)
app.include_router(data_router)
app.include_router(data_sources_router)
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
def health_check() -> JSONResponse:
    healthy = _db_ready and _scheduler_ready
    body = {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if _db_ready else "error",
        "scheduler": "ok" if _scheduler_ready else "error",
    }
    return JSONResponse(
        status_code=200 if healthy else 503,
        content=body,
    )


@app.get("/")
def root() -> dict:
    return {
        "title": app.title,
        "version": app.version,
        "docs_url": "/docs",
    }


# 生产模式：挂载前端构建产物（frontend/dist）。SPA fallback 由 html=True
# 自动处理（所有非 /api 路径都返回 index.html，由 React Router 接管路由）。
# 仅在 dist 存在时挂载，避免开发期出现"找不到 dist"错误。
_dist_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
    "dist",
)
if os.path.isdir(_dist_dir):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="spa")
    logger.info("已挂载前端构建产物: {}", _dist_dir)
else:
    logger.info("frontend/dist 不存在，跳过挂载（开发模式请手动启动 Vite）")
