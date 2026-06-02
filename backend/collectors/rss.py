import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class RSSProvider(BaseProvider):
    """通用 RSS 新闻采集提供者，通过 HTTP GET 获取 RSS feed 并解析。"""

    # 常见 RSS 命名空间 URI 映射（用于带前缀的标签查找）
    _NAMESPACES: dict[str, str] = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "atom": "http://www.w3.org/2005/Atom",
    }
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
        # 优先用 feedparser 解析（容错性好，能处理非标准 RSS/Atom）
        items = self._parse_with_feedparser(text)
        if items:
            return items
        # 回退：xml.etree.ElementTree
        return self._parse_with_etree(text)

    def _parse_with_etree(self, text: str) -> list[dict]:
        results: list[dict] = []
        try:
            # 注册常见命名空间以支持带前缀的标签查找
            for prefix, uri in RSSProvider._NAMESPACES.items():
                ET.register_namespace(prefix, uri)
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
            summary = self._get_text(item, "description") or ""
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

    def _parse_with_feedparser(self, text: str) -> list[dict]:
        """使用 feedparser 解析 RSS/Atom，容错性优于 xml.etree。"""
        results: list[dict] = []
        try:
            d = feedparser.parse(text)
        except Exception as e:
            logger.warning("feedparser 解析异常: provider={}, error={}", self.name, e)
            return results

        for entry in d.entries:
            title = entry.get("title", "").strip()
            if not title:
                continue
            link = entry.get("link", "")
            published_at = entry.get("published", "") or entry.get("updated", "")
            summary = entry.get("summary", "").strip()
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            if not content:
                content = entry.get("description", "")
            if not content:
                content = summary
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

def _get_text(element: ET.Element, tag: str) -> str:
        # 尝试直接查找（不带命名空间）
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()

        # 尝试命名空间查找（prefix:localname 格式）
        if ":" in tag:
            prefix, local_name = tag.split(":", 1)
            ns_uri = RSSProvider._NAMESPACES.get(prefix)
            if ns_uri is not None:
                child = element.find(f"{{{ns_uri}}}{local_name}")
                if child is not None and child.text:
                    return child.text.strip()

            # 回退：遍历子元素匹配本地名（兼容未注册命名空间的情况）
            for child in element:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == local_name and child.text:
                    return child.text.strip()
        return ""
