"""MarketLens 统一启动器（scripts/launcher.py）。

职责：
1. 在 asyncio 主事件循环中启动 uvicorn（端口 8000）。
2. 派生 streamlit 子进程（端口 8501），统一生命周期管理。
3. 等待 streamlit 端口就绪后自动打开默认浏览器到 UI。
4. 捕获 KeyboardInterrupt / SIGTERM，优雅关闭 streamlit 子进程。

调用方式：
    uv run python scripts/launcher.py     # CLI
    start.bat                              # Windows 双击
    start.sh                               # Linux/Mac 终端

设计依据（2026-06-08 调研）：
- Streamlit 无编程 API 可嵌入 FastAPI（GitHub issue #13600），唯一可行路径是子进程。
- `_HttpClientMixin` 的懒加载 + `_WRITE_LOCK` 跨 event loop 安全，子进程不共享内存。
- `%APPDATA%\\MarketLens\\` 数据目录由 `backend/config.py` 解析，
  本文件不直接处理（避免与 config 重复实现）。

历史：本文件原名 `main_exe.py`（2026-06-08），因命名易让人误以为是 Nuitka 打包
产物二进制，于 2026-06-09 改为 `launcher.py`。Nuitka 单 exe 打包路径已
确认放弃（单用户本地工具，参见 CLAUDE.md "Project context"）。
"""

from __future__ import annotations

import asyncio
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

# 0) 把 project_root 加进 sys.path,保证 ``from backend.*`` 在模块顶层就能 import
#    (uv run python scripts/main_exe.py 时,``''``(cwd) 在 sys.path,但 ``backend/``
#     作为子目录不会被自动发现;在 Nuitka onefile 模式下 ``__file__`` 指解压路径,
#     同理要显式插入)
if getattr(sys, "frozen", False):
    # Nuitka onefile 模式:__file__ 指向解压目录
    _project_root = Path(__file__).resolve().parent.parent
else:
    _project_root = Path(__file__).resolve().parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from loguru import logger  # noqa: E402

# 1) 初始化日志(必须在第一次 logger 使用前)
from backend.logging_config import setup_logging  # noqa: E402

setup_logging()

# Windows 上需要 SELECT 事件循环策略；Nuitka 打包后子进程也用相同策略。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _install_windows_ctrl_handler(stop_event: asyncio.Event) -> None:
    """注册 Windows Console Ctrl Handler(覆盖默认强制 kill 行为)。

    默认情况下,Windows 控制台关闭时,Python 进程被 TerminateProcess 强杀,
    不会执行 atexit / finally / signal handler。SetConsoleCtrlHandler 让
    我们能在 Ctrl+C / Ctrl+Break / 关窗事件 收到时主动通知主循环退出。
    """
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(ctrl_type: int) -> int:
        # 0=CTRL_C, 1=CTRL_BREAK, 2=CTRL_CLOSE(关窗), 5=CTRL_LOGOFF, 6=CTRL_SHUTDOWN
        # 全部走同一路径:通知主循环 + 5s 超时后强杀兜底
        logger.info("收到 Windows 控制事件 {},主动通知主循环", ctrl_type)
        stop_event.set()
        import threading
        threading.Timer(5.0, lambda: ctypes.windll.kernel32.ExitProcess(0)).start()  # type: ignore[attr-defined]
        return 1  # TRUE: 已处理

    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)  # type: ignore[attr-defined]


def _resolve_project_root() -> Path:
    """定位项目根目录。

    开发态：scripts/main_exe.py 的父目录的父目录。
    打包态：sys.executable 所在目录的父目录（onefile 会解压到 temp，
    但 streamlit 子进程的 cwd 必须指向真实项目根，否则 ui/app.py 找不到）。
    """
    if getattr(sys, "frozen", False):
        # Nuitka onefile 模式：sys.executable 指向临时解压目录，不可用。
        # 退回到打包时的工作目录（通过 __NUITKA_ONEFILE_PARENT__ 推断或当前 cwd）。
        return Path.cwd()
    return Path(__file__).resolve().parent.parent


def _spawn_streamlit_child(
    project_root: Path,
    port: int,
) -> subprocess.Popen:
    """派生 streamlit 子进程。"""
    cmd: list[str] = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "ui/app.py",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    logger.info("派生 streamlit 子进程: {}", " ".join(cmd))
    kwargs: dict = {
        "cwd": str(project_root),
        "stdout": subprocess.DEVNULL,  # 避免阻塞主进程 stdout 缓冲
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP 让 Ctrl+C 只发给主进程，terminate 子进程可控
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(cmd, **kwargs)


async def _wait_for_url(url: str, timeout: float = 15.0) -> bool:
    """轮询 URL，等待 streamlit 端口就绪。"""
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
    """等 streamlit 起来后弹浏览器。失败也不阻塞主流程。"""
    if await _wait_for_url(url, timeout=20.0):
        logger.info("UI 已就绪，自动打开浏览器: {}", url)
        webbrowser.open(url)
    else:
        logger.warning("UI 在 20s 内未就绪，请手动访问: {}", url)


def _terminate_streamlit(proc: subprocess.Popen) -> None:
    """优雅终止 streamlit 子进程，5s 超时后强杀。"""
    if proc.poll() is not None:
        return
    logger.info("清理 streamlit 子进程 PID={}", proc.pid)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("streamlit 5s 内未退出，强制 kill")
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.error("streamlit 子进程无法 kill,可能残留")


async def _run(stop_event: asyncio.Event | None = None) -> None:
    """主入口：拉子进程 + uvicorn 跑 FastAPI + 弹浏览器。

    Args:
        stop_event: 外部信号触发时会被 set,主循环检测到后让 uvicorn 优雅退出。
    """
    project_root = _resolve_project_root()
    logger.info("MarketLens 单 exe 启动器启动, project_root={}", project_root)

    # 0) 把 project_root 加进 sys.path,保证 `backend.main:app` 的字符串导入
    # 能找到模块(Nuitka 打包后 sys.path 不含 cwd;开发态 + uv 也未必含)
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
        logger.debug("已注入 sys.path: {}", project_root_str)

    # 1) 派生 streamlit 子进程
    streamlit_proc = _spawn_streamlit_child(project_root, port=8501)

    # 2) 后台任务:轮询端口 + 弹窗(不阻塞 uvicorn 启动)
    browser_task = asyncio.create_task(
        _open_browser_when_ready("http://127.0.0.1:8501")
    )

    # 3) 启动 uvicorn
    api_config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        lifespan="on",
    )
    api_server = uvicorn.Server(api_config)

    # 4) 监听 stop_event,信号来了主动通知 uvicorn 退出
    async def _watch_stop() -> None:
        if stop_event is None:
            return
        await stop_event.wait()
        logger.info("收到 stop_event,通知 uvicorn 退出")
        api_server.should_exit = True

    if stop_event is not None:
        task = asyncio.create_task(_watch_stop())
        # 给后台任务一个名字,finally 块方便找到并 cancel
        task.set_name("_watch_stop")

    try:
        await api_server.serve()
    finally:
        # 5) uvicorn 退出后,清理 streamlit 子进程 + 取消 watch_stop 后台任务
        if stop_event is not None:
            watch_task = next(
                (t for t in asyncio.all_tasks() if t.get_name() == "_watch_stop"),
                None,
            )
            if watch_task is not None and not watch_task.done():
                watch_task.cancel()
                try:
                    await watch_task
                except (asyncio.CancelledError, Exception):
                    pass
        browser_task.cancel()
        try:
            await browser_task
        except (asyncio.CancelledError, Exception):
            pass
        _terminate_streamlit(streamlit_proc)
        logger.info("MarketLens 单 exe 启动器退出")


def main() -> None:
    """CLI 入口,优雅处理 Ctrl+C / Ctrl+Break / 控制台关窗事件。

    Windows 行为：
    - 默认关窗 = TerminateProcess 强杀,atexit / signal 都不跑
    - 用 SetConsoleCtrlHandler 注册自定义 handler,主进程收到事件时
      通知主循环优雅退出;若 5 秒内未响应,Windows 仍会强杀
    - SIGBREAK (Ctrl+Break) 在 cmd / Git Bash 默认可用,行为同 Ctrl+C
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()

    if sys.platform == "win32":
        _install_windows_ctrl_handler(stop_event)
    else:
        # POSIX 下 SIGINT (Ctrl+C) 默认触发 KeyboardInterrupt,uvicorn 也能响应
        loop.add_signal_handler(signal.SIGINT, stop_event.set)  # type: ignore[attr-defined]

    try:
        # serve() 会在 stop_event 被 set 时继续跑完当前请求,然后由 finally 清理
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
