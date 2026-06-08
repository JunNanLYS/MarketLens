import asyncio
import json
import re
import sys
from datetime import datetime, timezone
import os
from pathlib import Path

from loguru import logger
from backend.collectors.base import NewsProvider

# CLI 搜索路径：优先从环境变量 TENCT_NEWS_CLI_PATH 获取；固定路径下查找安装的 skill。
# 安全考量：不读取 CODEX_HOME 等未签名环境变量覆盖安装路径，
# 防止恶意进程通过环境变量劫持 CLI 路径执行任意代码。
_ENV_CLI_PATH = os.environ.get("TENCT_NEWS_CLI_PATH")
SKILL_DIR = Path.home() / ".codex" / "skills" / "tencent-news"
GLOBAL_DIR = Path.home() / ".tencent-news-cli" / "bin"
# 跨平台二进制名：Windows 加 .exe 后缀
if sys.platform == "win32":
    BIN_NAME = "tencent-news-cli.exe"
else:
    BIN_NAME = "tencent-news-cli"


class TencentNewsProvider(NewsProvider):
    """腾讯新闻 Provider，通过 CLI 调用外部工具（异步版）。

    该 Provider 通过调用本地安装的 tencent-news-cli 命令行工具获取新闻数据，
    适用于本地未提供直连 API 的腾讯新闻源。主要职责：
    1. 启动时通过 _find_cli 探测 CLI 可执行文件位置（环境变量、PATH、全局目录、Skill 目录）。
    2. 通过 asyncio.create_subprocess_exec 异步执行子进程，避免阻塞事件循环。
    3. 支持 hot（热点新闻）和 search（关键词搜索）两种命令，并将 CLI 文本/JSON 输出
       统一解析为标准化的新闻字典结构。
    4. 当 CLI 缺失时通过 _cli_disabled 标志位短路，避免每次采集周期重复探测和重复警告。
    """

    def __init__(
        self,
        name: str,
        timeout: int = 30,
        params: dict | None = None,
        optional: bool = True,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._cli_path: str | None = None
        self._cli_disabled: bool = False
        # 连续超时计数器：累计达到阈值后触发 disable，避免每次采集周期重复超时重试
        self._consecutive_timeouts: int = 0
        self._max_items: int = int(params.get("max_items", 50)) if params else 50

    def _find_cli(self) -> str | None:
        import shutil

        search_paths = [
            shutil.which(BIN_NAME),
            GLOBAL_DIR / BIN_NAME,
            SKILL_DIR / BIN_NAME,
            Path(__file__).resolve().parent.parent.parent / "bin" / BIN_NAME,
        ]
        if _ENV_CLI_PATH:
            search_paths.insert(0, Path(_ENV_CLI_PATH))
        for p in search_paths:
            if p and Path(p).exists():
                return str(p)
        return None

    def _ensure(self) -> bool:
        if self._cli_path:
            return True
        if self._cli_disabled:
            return False
        p = self._find_cli()
        if p:
            self._cli_path = p
            logger.info("TencentNews CLI found: {}", p)
            return True
        self._cli_disabled = True
        logger.warning("TencentNews CLI not available")
        return False

    async def _run(
        self, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[str | None, str | None]:
        if not self._ensure():
            return None, "CLI not installed"
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                # 累计连续超时：达到阈值后 disable provider，避免每周期重复超时
                self._consecutive_timeouts += 1
                if self._consecutive_timeouts >= 3 and not self._cli_disabled:
                    self._cli_disabled = True
                    logger.warning(
                        "TencentNews CLI 连续超时 {} 次，自动 disable provider",
                        self._consecutive_timeouts,
                    )
                return None, "Timeout"
        except Exception as e:
            return None, str(e)
        # 执行成功：重置连续超时计数
        self._consecutive_timeouts = 0
        if proc.returncode != 0:
            stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
            stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
            return None, (stderr or stdout or "").strip()[:200]
        return stdout_bytes.decode(errors="replace") if stdout_bytes else "", None

    def _parse_json(self, text: str) -> list[dict]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        items = (
            data if isinstance(data, list) else data.get("data", data.get("items", []))
        )
        if not isinstance(items, list):
            return []
        out = []
        for item in items[: self._max_items]:
            title = item.get("title") or item.get("news_title") or ""
            if not title:
                continue
            ts = (
                item.get("publish_time")
                or item.get("publishTime")
                or item.get("pub_time")
            )
            published_at = None
            if ts:
                if isinstance(ts, (int, float)):
                    published_at = datetime.fromtimestamp(
                        ts, tz=timezone.utc
                    ).isoformat()
                else:
                    published_at = str(ts)
            out.append(
                {
                    "title": title,
                    "source": item.get("source")
                    or item.get("media_name")
                    or "腾讯新闻",
                    "url": item.get("url") or item.get("link") or "",
                    "content": item.get("content") or item.get("summary") or "",
                    "summary": item.get("summary") or item.get("abstract") or "",
                    "published_at": published_at,
                    "sentiment": "neutral",
                    "importance": "normal",
                    "collected_at": self._now(),
                }
            )
        return out

    def _parse_table(self, text: str) -> list[dict]:
        out = []
        for line in text.strip().split("\n"):
            s = line.strip()
            if s.startswith("|") and len(s.split("|")) >= 3:
                title = s.split("|")[1].strip()
                if title and not re.match(r"^[\s\-:|]+$", title):
                    out.append(
                        {
                            "title": title,
                            "source": "腾讯新闻",
                            "url": "",
                            "content": "",
                            "summary": "",
                            "published_at": None,
                            "sentiment": "neutral",
                            "importance": "normal",
                            "collected_at": self._now(),
                        }
                    )
        return out

    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        apikey = (self.params or {}).get("apikey", "")
        # 优先通过环境变量 TENCENT_NEWS_APIKEY 传递 apikey，避免在命令行参数中明文泄露。
        # 安全考量：不提供 --caller fallback（旧版 CLI 不支持 env 时应升级 CLI 而非降级安全）：
        # Linux/macOS 的 /proc/<pid>/cmdline 进程列表对同用户进程可见，
        # 命令行参数会泄露 API Key。仅依赖环境变量透传。
        run_env: dict[str, str] | None = None
        if apikey:
            run_env = os.environ.copy()
            run_env["TENCENT_NEWS_APIKEY"] = apikey
        cmds: list[list[str]] = [["hot", "--limit", str(self._max_items)]]
        cmds.append(["search", "财经", "--limit", str(self._max_items)])
        for cmd in cmds:
            out, err = await self._run(cmd, env=run_env)
            if not err and out:
                items = self._parse_json(out) or self._parse_table(out)
                if items:
                    logger.info("TencentNews fetched {} items", len(items))
                    return items
        return []
