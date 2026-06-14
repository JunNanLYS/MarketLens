import asyncio
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
from backend.api.settings import router as settings_router
from backend.api.tasks import router as tasks_router
from backend.api.tasks import _set_scheduler
from backend.config import get_config
from backend.config_runtime import get_config_store
from backend.scheduler.jobs import SchedulerManager
from backend.storage.schema import init_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """注入常用安全响应头，抑制 XSS/点击劫持/MIME 嗅探/信息泄露。

    - X-Content-Type-Options: nosniff — 禁止浏览器进行 MIME 嗅探。
    - X-Frame-Options: DENY — 禁止任何 iframe 嵌入。
    - Referrer-Policy: no-referrer — 出口链路不携带来源。
    - Strict-Transport-Security: 仅当 ``security.enable_hsts: true`` 显式开启时注入。
      本地工具走 HTTP 无意义；若误启用并访问过 HTTPS，浏览器会缓存 HSTS 2 年。
    - Content-Security-Policy: 保持宽松（FastAPI Swagger UI 需要 inline script/style）。
    """

    def __init__(self, app, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: StarletteRequest, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if self._enable_hsts:
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
_main_loop: asyncio.AbstractEventLoop | None = None


def _provider_reload_hook(new_cfg: dict) -> None:
    """ConfigStore reload 钩子：让 CollectionService / NewsService 用新配置重建 Provider。

    钩子可能在 starlette threadpool（PATCH /settings 走 sync 路由）或主 event loop
    中被调用。Provider 的 httpx.AsyncClient 必须在**它被创建的 loop** 上 close —— 否则
    httpx 0.27+ 会抛 ``RuntimeError: ... different loop``。

    解法：把 reload 协程提交到 lifespan 阶段抓取的主 loop（``_main_loop``）上执行；
    钩子线程同步等待 future。任何 Service 失败都只 log，不抛——避免一个钩子崩了整个 PATCH。
    """
    from backend.scheduler.jobs import _get_collection_service, _get_news_service

    if _main_loop is None or _main_loop.is_closed():
        logger.warning("主 event loop 不可用，Provider reload 跳过（重启后生效）")
        return

    async def _reload_all() -> None:
        for label, getter in (
            ("CollectionService", _get_collection_service),
            ("NewsService", _get_news_service),
        ):
            try:
                await getter().reload_providers(new_cfg)
            except Exception:
                logger.exception("{} reload_providers 失败", label)

    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None

    if current is _main_loop:
        # 主 loop 内调用（例如启动期 reload）：直接调度
        _main_loop.create_task(_reload_all())
        return

    # 跨线程：worker thread → 主 loop。同步等结果以保证 PATCH 返回时 reload 已完成。
    future = asyncio.run_coroutine_threadsafe(_reload_all(), _main_loop)
    try:
        future.result(timeout=30)
    except Exception:
        logger.exception("Provider reload 在主 loop 上执行失败")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_manager, _db_ready, _scheduler_ready, _main_loop
    _main_loop = asyncio.get_running_loop()
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
        # 注册 ConfigStore reload 钩子：
        # 1) Scheduler reload —— scheduler.tasks.*.interval 变更立即生效
        # 2) Service Provider reload —— data_sources.*.enabled / .timeout 变更立即生效
        store = get_config_store()
        store.register_reload_hook(_scheduler_manager.reload)
        store.register_reload_hook(_provider_reload_hook)
        logger.info("MarketLens 应用已启动")
    except Exception:
        logger.exception("调度器启动失败")
    yield
    if _scheduler_manager is not None:
        _scheduler_manager.shutdown()
    # 通过 Service 的公开关闭入口统一释放 Provider 资源，避免生命周期层
    # 直接访问 Service 私有成员；单个 Service/Provider 失败也不阻断其余清理。
    from backend.scheduler.jobs import _get_collection_service, _get_news_service

    try:
        await _get_collection_service().close_providers()
        await _get_news_service().close_providers()
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
_enable_hsts = bool(config.get("security", {}).get("enable_hsts", False))
app.add_middleware(SecurityHeadersMiddleware, enable_hsts=_enable_hsts)
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
app.include_router(settings_router)


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
async def health_check() -> JSONResponse:
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
async def root() -> dict:
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
