from html.parser import HTMLParser
from urllib.parse import quote_plus

import httpx
from loguru import logger

from backend.collectors.base import NewsProvider, _HttpClientMixin


class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._tag_stack = []
        self._current_link = ""
        self._current_text = ""
        self._in_result = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith("#") and not href.startswith("/"):
                self._current_link = href
                self._in_result = True
                self._current_text = ""
        elif self._in_result and tag in ("b", "strong", "span", "div"):
            self._tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._in_result and tag == "a":
            text = self._current_text.strip()
            if text and self._current_link:
                self.results.append({"title": text, "url": self._current_link})
            self._current_link = ""
            self._current_text = ""
            self._in_result = False
        elif self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_result:
            self._current_text += data


class SearchEngineNewsProvider(NewsProvider, _HttpClientMixin):
    """多搜索引擎新闻提供者（异步版）。"""

    DEFAULT_ENGINES = {
        "duckduckgo": {
            "url": "https://duckduckgo.com/html/?q={keyword}",
            "name": "DuckDuckGo",
        },
        "bing": {
            "url": "https://cn.bing.com/search?q={keyword}&ensearch=0",
            "name": "Bing",
        },
        "sogou": {
            "url": "https://sogou.com/web?query={keyword}",
            "name": "Sogou",
        },
    }

    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = True) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        engines_cfg = self.params.get("engines", {}) if params else {}
        self._engines = engines_cfg or dict(SearchEngineNewsProvider.DEFAULT_ENGINES)
        self._primary = self.params.get("primary_engine", "duckduckgo") if params else "duckduckgo"
        self._keywords = self.params.get("keywords", []) if params else []
        self._max_items = int(self.params.get("max_items", 30)) if params else 30
        # 懒加载 httpx.AsyncClient：见 _HttpClientMixin 注释
        self._client: httpx.AsyncClient | None = None
        self._client_headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _client_kwargs(self) -> dict:
        """覆写 mixin 钩子，注入浏览器 headers + follow_redirects。"""
        return {
            "timeout": httpx.Timeout(self.timeout),
            "follow_redirects": True,
            "headers": self._client_headers,
        }


    def _build_query(self, base_keywords: list[str] | None = None) -> str:
        parts = []
        if base_keywords:
            parts.extend(base_keywords)
        if self._keywords:
            parts.extend(self._keywords)
        if not parts:
            parts = ["\u8d22\u7ecf", "\u80a1\u5e02", "\u6295\u8d44"]
        return " ".join(parts)

    async def _fetch_engine(self, engine_name: str, keyword: str) -> list[dict]:
        engine = self._engines.get(engine_name)
        if not engine:
            return []
        url = engine["url"].replace("{keyword}", quote_plus(keyword))
        try:
            client = await self._get_client()
            resp = await client.get(url)
            resp.raise_for_status()
            extractor = _LinkExtractor()
            extractor.feed(resp.text)
            results = []
            for item in extractor.results[:self._max_items]:
                results.append({
                    "title": item["title"],
                    "source": engine.get("name", engine_name),
                    "url": item["url"],
                    "content": "",
                    "summary": "",
                    "published_at": None,
                    "sentiment": "neutral",
                    "importance": "normal",
                    "collected_at": self._now(),
                })
            logger.info("{} 搜索到 {} 条结果", engine.get("name"), len(results))
            return results
        except httpx.TimeoutException:
            logger.warning("{} 超时", engine.get("name"))
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("{} HTTP 错误: {}", engine.get("name"), e.response.status_code)
            return []
        except Exception as e:
            logger.warning("{} 异常: {}", engine.get("name"), e)
            return []

    async def fetch_news(self, keywords: list[str] | None = None) -> list[dict]:
        query = self._build_query(keywords)
        results = await self._fetch_engine(self._primary, query)
        if not results:
            for name in self._engines:
                if name != self._primary:
                    results = await self._fetch_engine(name, query)
                    if results:
                        break
        return results

    async def search(self, keyword: str) -> list[dict]:
        """搜索入口：委托给 fetch_news，保持与旧 BaseProvider.search 签名兼容。"""
        return await self.fetch_news([keyword])
