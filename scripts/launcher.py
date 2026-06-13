"""MarketLens 统一启动器（scripts/launcher.py）。

职责：
1. 在 asyncio 主事件循环中启动 uvicorn（端口 8000）。
2. 派生 Vite dev server 子进程（端口 5173，仅 dev 模式）。
3. 等待前端端口就绪后自动打开默认浏览器到 UI。
4. 捕获 KeyboardInterrupt / SIGTERM，优雅关闭前端子进程。

调用方式：
    uv run python scripts/launcher.py     # CLI
    start.bat                              # Windows 双击
    start.sh                               # Linux/Mac 终端

设计依据（2026-06-10 调研）：
- React 前端与 FastAPI 通过 /api/v1/* + /openapi.json 通信，本地工具采用单端口
  部署：dev 模式 Vite 代理 /api → FastAPI，prod 模式 FastAPI 挂载 frontend/dist。
- Vite dev server 必须作为子进程派生（无 Python in-process 等价物）。
- `%APPDATA%\\MarketLens\\` 数据目录由 `backend/config.py` 解析，
  本文件不直接处理（避免与 config 重复实现）。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TextIO

# 0) 把 project_root 加进 sys.path，保证 ``from backend.*`` 在模块顶层就能 import
if getattr(sys, "frozen", False):
    _project_root = Path(__file__).resolve().parent.parent
else:
    _project_root = Path(__file__).resolve().parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from loguru import logger  # noqa: E402

# 1) 初始化日志（必须在第一次 logger 使用前）
from backend.config import get_data_dir  # noqa: E402
from backend.logging_config import setup_logging  # noqa: E402

setup_logging()

# Windows 上需要 SELECT 事件循环策略
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _install_windows_ctrl_handler(stop_event: asyncio.Event) -> None:
    """注册 Windows Console Ctrl Handler（覆盖默认强制 kill 行为）。"""
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(ctrl_type: int) -> int:
        logger.info("收到 Windows 控制事件 {},主动通知主循环", ctrl_type)
        stop_event.set()
        import threading
        threading.Timer(5.0, lambda: ctypes.windll.kernel32.ExitProcess(0)).start()  # type: ignore[attr-defined]
        return 1

    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)  # type: ignore[attr-defined]


def _resolve_project_root() -> Path:
    """定位项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent.parent


def _spawn_vite_child(project_root: Path, port: int) -> tuple[subprocess.Popen, TextIO]:
    """派生 Vite dev server 子进程，并把输出落到日志文件。"""
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("未找到 npm，请先安装 Node.js >= 18")

    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    vite_log_path = log_dir / "vite-dev.log"
    vite_log = vite_log_path.open("a", encoding="utf-8")

    cmd: list[str] = [
        npm,
        "--prefix",
        "frontend",
        "run",
        "dev",
        "--",
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
        "--strictPort",
    ]
    logger.info(
        "派生 Vite dev server: {}，日志文件={}",
        " ".join(cmd),
        vite_log_path,
    )
    kwargs: dict[str, object] = {
        "cwd": str(project_root),
        "stdout": vite_log,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception:
        vite_log.close()
        raise
    return proc, vite_log


def _is_port_available(host: str, port: int) -> bool:
    """检查端口是否可绑定。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _ensure_port_available(host: str, port: int, service_name: str) -> None:
    """端口被占用时给出明确错误,避免半启动后再退出。"""
    if _is_port_available(host, port):
        return
    raise RuntimeError(
        f"{service_name} 端口 {host}:{port} 已被占用。"
        "请关闭已有 MarketLens/uvicorn/Vite 进程后重试。"
    )


async def _wait_for_url(url: str, timeout: float = 20.0) -> bool:
    """轮询 URL，等待前端端口就绪。"""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(url, timeout=1.0)
                if resp.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout):
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug("端口探测异常: {}", e)
                await asyncio.sleep(0.3)
    return False


async def _open_browser_when_ready(url: str) -> None:
    """等前端起来后弹浏览器。失败也不阻塞主流程。"""
    if await _wait_for_url(url, timeout=30.0):
        logger.info("UI 已就绪，自动打开浏览器: {}", url)
        webbrowser.open(url)
    else:
        logger.warning("UI 在 30s 内未就绪，请手动访问: {}", url)


def _terminate_child(proc: subprocess.Popen, name: str) -> None:
    """优雅终止子进程，5s 超时后强杀。"""
    if proc.poll() is not None:
        return
    logger.info("清理子进程 {} PID={}", name, proc.pid)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("{} 5s 内未退出，强制 kill", name)
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.error("{} 子进程无法 kill,可能残留", name)


async def _run(stop_event: asyncio.Event | None = None) -> None:
    """主入口：拉 Vite 子进程 + uvicorn 跑 FastAPI + 弹浏览器。"""
    project_root = _resolve_project_root()
    logger.info("MarketLens 启动器启动, project_root={}", project_root)

    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
        logger.debug("已注入 sys.path: {}", project_root_str)

    # 0) 决定 dev / prod 模式
    # 默认开发模式（Vite dev server 5173 + backend 8000），
    # 仅在显式设置 MARKETLENS_PROD=1 时走生产模式（单端口 8000 挂载 frontend/dist）。
    # 原来的 _frontend_dist_exists 判断会导致开发期误走生产模式（dist 残留），
    # 改为纯环境变量驱动，避免开发期忘记清 dist 就弹到静态挂载。
    is_prod = os.environ.get("MARKETLENS_PROD") == "1"
    frontend_proc: subprocess.Popen | None = None
    vite_log_handle: TextIO | None = None
    browser_task: asyncio.Task[None] | None = None
    watch_task: asyncio.Task[None] | None = None
    frontend_url: str

    _ensure_port_available("127.0.0.1", 8000, "FastAPI 后端")
    if not is_prod:
        _ensure_port_available("127.0.0.1", 5173, "Vite 前端")

    if is_prod:
        # 生产模式：FastAPI 挂载 frontend/dist，单进程单端口（8000）
        frontend_url = "http://127.0.0.1:8000"
        logger.info("生产模式：FastAPI 挂载 frontend/dist，单端口 {}", frontend_url)
    else:
        # 开发模式：派生 Vite dev server（5173）+ FastAPI（8000），Vite 代理 /api
        frontend_url = "http://127.0.0.1:5173"
        frontend_proc, vite_log_handle = _spawn_vite_child(project_root, port=5173)
        browser_task = asyncio.create_task(_open_browser_when_ready(frontend_url))

    # 1) 启动 uvicorn
    api_config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        lifespan="on",
    )
    api_server = uvicorn.Server(api_config)

    # 2) 监听 stop_event
    async def _watch_stop() -> None:
        if stop_event is None:
            return
        await stop_event.wait()
        logger.info("收到 stop_event,通知 uvicorn 退出")
        api_server.should_exit = True

    if stop_event is not None:
        watch_task = asyncio.create_task(_watch_stop())

    try:
        await api_server.serve()
    finally:
        if watch_task is not None and not watch_task.done():
            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass
        if frontend_proc is not None:
            _terminate_child(frontend_proc, "Vite dev server")
        if vite_log_handle is not None:
            vite_log_handle.close()
        if browser_task is not None:
            browser_task.cancel()
            try:
                await browser_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("MarketLens 启动器退出")


def main() -> None:
    """CLI 入口，优雅处理 Ctrl+C / Ctrl+Break / 控制台关窗事件。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()

    if sys.platform == "win32":
        _install_windows_ctrl_handler(stop_event)
    else:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)  # type: ignore[attr-defined]

    try:
        loop.run_until_complete(_run(stop_event))
    except KeyboardInterrupt:
        logger.info("用户中断,MarketLens 退出")
    except Exception:
        logger.exception("MarketLens 启动器异常退出")
        sys.exit(1)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
