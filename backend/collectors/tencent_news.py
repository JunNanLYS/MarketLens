"""Tencent News data source provider."""

import subprocess
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from backend.collectors.base import BaseProvider

SKILL_DIR = Path("C:/Users/18906/.codex/skills/tencent-news")
GLOBAL_DIR = Path.home() / ".tencent-news-cli" / "bin"
BIN_NAME = "tencent-news-cli.exe"


class TencentNewsProvider(BaseProvider):
    """Tencent News provider using CLI."""

    def __init__(self, name, timeout=30, params=None, optional=True):
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._cli_path = None
        self._max_items = int(params.get("max_items", 50)) if params else 50

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _find_cli(self):
        import shutil
        for p in [shutil.which(BIN_NAME), GLOBAL_DIR / BIN_NAME, SKILL_DIR / BIN_NAME, Path(__file__).resolve().parent.parent.parent / "bin" / BIN_NAME]:
            if p and Path(p).exists():
                return str(p)
        return None

    def _ensure(self):
        if self._cli_path:
            return True
        p = self._find_cli()
        if p:
            self._cli_path = p
            logger.info("TencentNews CLI found: {}", p)
            return True
        logger.warning("TencentNews CLI not available")
        return False

    def _run(self, args):
        if not self._ensure():
            return None, "CLI not installed"
        try:
            r = subprocess.run([self._cli_path] + args, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return None, "Timeout"
        except Exception as e:
            return None, str(e)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout or "").strip()[:200]
        return r.stdout, None

    def _parse_json(self, text):
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

    def _parse_table(self, text):
        out = []
        for line in text.strip().split("\n"):
            s = line.strip()
            if s.startswith("|") and len(s.split("|")) >= 3:
                title = s.split("|")[1].strip()
                if title and not re.match(r"^[\s\-:|]+$", title):
                    out.append({"title": title, "source": "\u817e\u8baf\u65b0\u95fb", "url": "", "content": "", "summary": "", "published_at": None, "sentiment": "neutral", "importance": "normal", "collected_at": self._now()})
        return out

    def fetch_news(self):
        for cmd in [["hot", "--limit", str(self._max_items)], ["news", "hot", "--limit", str(self._max_items)]]:
            out, err = self._run(cmd)
            if not err and out:
                items = self._parse_json(out) or self._parse_table(out)
                if items:
                    logger.info("TencentNews fetched {} items", len(items))
                    return items
        return []

    def search(self, keyword): return []
    def quote(self, symbols): return []
    def kline(self, symbol, period="daily"): return []
    def finance(self, symbol): return {}
    def fund_flow(self, symbol): return {}
    def technical(self, symbol): return {}
