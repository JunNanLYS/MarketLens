import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class RSSProvider(BaseProvider):
    """通用 RSS 新闻采集提供者，通过 HTTP GET 获取 RSS feed 并解析。"""

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.url: str = self.params.get("url", "")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def search(self, keyword: str) -> list[dict]:
        return []

    def quote(self, symbols: list[str]) -> list[dict]:
        return []

    def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    def finance(self, symbol: str) -> dict:
        return {}

    def fund_flow(self, symbol: str) -> dict:
        return {}

    def technical(self, symbol: str) -> dict:
        return {}

    def fetch_news(self) -> list[dict]:
        if not self.url:
            logger.warning("RSS 源 URL 未配置: provider={}", self.name)
            return []
        try:
            resp = httpx.get(self.url, timeout=self.timeout, follow_redirects=True)
            resp.raise_for_status()
            return self._parse_rss(resp.text)
        except httpx.TimeoutException:
            logger.warning("RSS 请求超时: url={}, timeout={}s", self.url, self.timeout)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("RSS HTTP 错误: url={}, status={}", self.url, e.response.status_code)
            return []
        except Exception as e:
            logger.error("RSS 请求异常: url={}, error={}", self.url, e)
            return []

    def _parse_rss(self, text: str) -> list[dict]:
        results: list[dict] = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            logger.error("RSS XML 解析失败: provider={}, error={}", self.name, e)
            return []

        items = root.findall(".//item")
        if not items:
            channel = root.find("channel")
            if channel is not None:
                items = channel.findall("item")

        for item in items:
            title = self._get_text(item, "title")
            link = self._get_text(item, "link")
            published_at = self._get_text(item, "pubDate")
            summary = self._get_text(item, "description")
            content = self._get_text(item, "content:encoded") or self._get_text(item, "description")
            results.append({
                "title": title,
                "source": self.name,
                "url": link,
                "published_at": published_at,
                "summary": summary,
                "content": content,
                "collected_at": self._now(),
            })
        return results

    @staticmethod
    def _get_text(element: ET.Element, tag: str) -> str:
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return ""
