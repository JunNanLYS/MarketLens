import asyncio
import json
import re
import sys
from datetime import datetime, timezone
import os
from pathlib import Path

from loguru import logger
from backend.collectors.base import BaseProvider

# CLI 搜索路径：优先从环境变量 TENCT_NEWS_CLI_PATH 获取，其次在 CODEX_HOME 或用户目录下的 skill 路径
_ENV_CLI_PATH = os.environ.get("TENCT_NEWS_CLI_PATH")
SKILL_DIR = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills" / "tencent-news"
GLOBAL_DIR = Path.home() / ".tencent-news-cli" / "bin"
# 跨平台二进制名：Windows 加 .exe 后缀
if sys.platform == "win32":
    BIN_NAME = "tencent-news-cli.exe"
else:
    BIN_NAME = "tencent-news-cli"


class TencentNewsProvider(BaseProvider):
    """Tencent News provider using CLI (async)."""

    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = True) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._cli_path = None
        self._max_items: int = int(params.get("max_items", 50)) if params else 50


    def _find_cli(self) -> str | None:
        import shutil
        search_paths = [shutil.which(BIN_NAME), GLOBAL_DIR / BIN_NAME, SKILL_DIR / BIN_NAME, Path(__file__).resolve().parent.parent.parent / "bin" / BIN_NAME]
        if _ENV_CLI_PATH:
            search_paths.insert(0, Path(_ENV_CLI_PATH))
        for p in search_paths:
            if p and Path(p).exists():
                return str(p)
        return None

    def _ensure(self) -> bool:
        if self._cli_path:
            return True
        p = self._find_cli()
        if p:
            self._cli_path = p
            logger.info("TencentNews CLI found: {}", p)
            return True
        logger.warning("TencentNews CLI not available")
        return False

    async def _run(self, args: list[str], env: dict[str, str] | None = None) -> tuple[str | None, str | None]:
        if not self._ensure():
            return None, "CLI not installed"
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli_path, *args,
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
                return None, "Timeout"
        except Exception as e:
            return None, str(e)
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
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        if not isinstance(items, list):
            return []
        out = []
        for item in items[:self._max_items]:
            title = item.get("title") or item.get("news_title") or ""
            if not title:
                continue
            ts = item.get("publish_time") or item.get("publishTime") or item.get("pub_time")
            published_at = None
            if ts:
                if isinstance(ts, (int, float)):
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                else:
                    published_at = str(ts)
            out.append({
                "title": title,
                "source": item.get("source") or item.get("media_name") or "\u817e\u8baf\u65b0\u95fb",
                "url": item.get("url") or item.get("link") or "",
                "content": item.get("content") or item.get("summary") or "",
                "summary": item.get("summary") or item.get("abstract") or "",
                "published_at": published_at,
                "sentiment": "neutral",
                "importance": "normal",
                "collected_at": self._now(),
            })
        return out

    def _parse_table(self, text: str) -> list[dict]:
        out = []
        for line in text.strip().split("\n"):
            s = line.strip()
            if s.startswith("|") and len(s.split("|")) >= 3:
                title = s.split("|")[1].strip()
                if title and not re.match(r"^[\s\-:|]+$", title):
                    out.append({"title": title, "source": "\u817e\u8baf\u65b0\u95fb", "url": "", "content": "", "summary": "", "published_at": None, "sentiment": "neutral", "importance": "normal", "collected_at": self._now()})
        return out

    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        apikey = (self.params or {}).get("apikey", "")
        # \u4f18\u5148\u901a\u8fc7\u73af\u5883\u53d8\u91cf\u4f20\u9012 apikey\uff0c\u907f\u514d\u5728\u547d\u4ee4\u884c\u53c2\u6570\u4e2d\u660e\u6587\u6cc4\u9732
        run_env: dict[str, str] | None = None
        if apikey:
            run_env = os.environ.copy()
            run_env["TENCENT_NEWS_APIKEY"] = apikey
        cmds: list[list[str]] = [["hot", "--limit", str(self._max_items)]]
        if apikey:
            # \u4fdd\u7559 --caller \u4f5c\u4e3a fallback\uff1a\u65e7\u7248 CLI \u53ef\u80fd\u4e0d\u8bc6\u522b env
            cmds[0].extend(["--caller", apikey])
        cmds.append(["search", "\u8d22\u7ecf", "--limit", str(self._max_items)])
        for cmd in cmds:
            out, err = await self._run(cmd, env=run_env)
            if not err and out:
                items = self._parse_json(out) or self._parse_table(out)
                if items:
                    logger.info("TencentNews fetched {} items", len(items))
                    return items
        return []

    async def search(self, keyword: str) -> list[dict]:
        return []
    async def quote(self, symbols: list[str]) -> list[dict]:
        return []
    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []
    async def finance(self, symbol: str) -> dict:
        return {}
    async def fund_flow(self, symbol: str) -> dict:
        return {}
    async def technical(self, symbol: str) -> dict:
        return {}
