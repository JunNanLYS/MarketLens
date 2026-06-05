import email.utils
import feedparser
import xml.etree.ElementTree as ET

import httpx
from loguru import logger

from backend.collectors.base import NewsProvider


class RSSProvider(NewsProvider):
    """通用 RSS 新闻采集提供者（异步版）。"""

    _NAMESPACES: dict[str, str] = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "atom": "http://www.w3.org/2005/Atom",
    }

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.url: str = self.params.get("url", "")
        # 懒加载 httpx.AsyncClient：避免 __init__ 阶段在 Windows + Python 3.13 上
        # 因 SSL/连接池初始化阻塞 3.8s+。首次 await 使用时再创建。
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """首次使用时创建 httpx 客户端，后续复用。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        if not self.url:
            logger.warning("RSS 源 URL 未配置: provider={}", self.name)
            return []
        try:
            client = await self._get_client()
            resp = await client.get(self.url)
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
        items = self._parse_with_feedparser(text)
        if items:
            return items
        return self._parse_with_etree(text)

    @staticmethod
    def _normalize_date(raw: str) -> str:
        """将 RSS 日期字符串转换为 ISO 8601 格式，解析失败则返回原字符串。"""
        if not raw:
            return raw
        try:
            dt = email.utils.parsedate_to_datetime(raw)
            return dt.isoformat()
        except Exception:
            return raw

    def _parse_with_etree(self, text: str) -> list[dict]:
        results: list[dict] = []
        try:
            # 命名空间前缀已在模块导入时一次性注册，此处不再重复调用
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
                "published_at": self._normalize_date(published_at),
                "summary": summary,
                "content": content,
                "collected_at": self._now(),
            })
        return results

    def _parse_with_feedparser(self, text: str) -> list[dict]:
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
                "published_at": self._normalize_date(published_at),
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

        if ":" in tag:
            prefix, local_name = tag.split(":", 1)
            ns_uri = RSSProvider._NAMESPACES.get(prefix)
            if ns_uri is not None:
                child = element.find(f"{{{ns_uri}}}{local_name}")
                if child is not None and child.text:
                    return child.text.strip()

            for child in element:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == local_name and child.text:
                    return child.text.strip()
        return ""


# 模块级一次性注册 XML 命名空间前缀，避免每次 fetch_news 重复调用
for _prefix, _uri in RSSProvider._NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)
