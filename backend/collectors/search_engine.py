"""Multi-search engine news provider.

利用多搜索引擎搜索财经新闻，无需 API Key。
默认使用 DuckDuckGo（无需 API Key），也可配置其他引擎。
"""

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote_plus

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class _LinkExtractor(HTMLParser):
    """从 HTML 中提取链接和标题。"""

    def __init__(self):
        super().__init__()
        self.results = []
        self._tag_stack = []
        self._current_link = ""
        self._current_text = ""
        self._in_result = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith("#") and not href.startswith("/"):
                self._current_link = href
                self._in_result = True
                self._current_text = ""
        elif self._in_result and tag in ("b", "strong", "span", "div"):
            self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if self._in_result and tag == "a":
            text = self._current_text.strip()
            if text and self._current_link:
                self.results.append({"title": text, "url": self._current_link})
            self._current_link = ""
            self._current_text = ""
            self._in_result = False
        elif self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._in_result:
            self._current_text += data


class SearchEngineNewsProvider(BaseProvider):
    """多搜索引擎新闻提供者。

    搜索财经新闻，支持配置多个搜索引擎。
    """

    # 默认搜索引擘配置
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

    def __init__(self, name, timeout=30, params=None, optional=True):
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        engines_cfg = self.params.get("engines", {}) if params else {}
        self._engines = engines_cfg or dict(SearchEngineNewsProvider.DEFAULT_ENGINES)
        self._primary = self.params.get("primary_engine", "duckduckgo") if params else "duckduckgo"
        self._keywords = self.params.get("keywords", []) if params else []
        self._max_items = int(self.params.get("max_items", 30)) if params else 30
        self._client = httpx.Client(timeout=self.timeout, follow_redirects=True)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _build_query(self, base_keywords=None):
        """构建搜索关键词。"""
        parts = []
        if base_keywords:
            parts.extend(base_keywords)
        if self._keywords:
            parts.extend(self._keywords)
        if not parts:
            parts = ["\u8d22\u7ecf", "\u80a1\u5e02", "\u6295\u8d44"]
        return " ".join(parts)

    def _fetch_engine(self, engine_name, keyword):
        """从指定搜索引擎获取结果。"""
        engine = self._engines.get(engine_name)
        if not engine:
            return []
        url = engine["url"].replace("{keyword}", quote_plus(keyword))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            resp = self._client.get(url, headers=headers)
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
            logger.info("{} \u641c\u7d22\u5230 {} \u6761\u7ed3\u679c", engine.get("name"), len(results))
            return results
        except httpx.TimeoutException:
            logger.warning("{} \u8d85\u65f6", engine.get("name"))
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("{} HTTP \u9519\u8bef: {}", engine.get("name"), e.response.status_code)
            return []
        except Exception as e:
            logger.warning("{} \u5f02\u5e38: {}", engine.get("name"), e)
            return []

    def fetch_news(self, keywords=None):
        """搜索财经新闻。"""
        query = self._build_query(keywords)
        results = self._fetch_engine(self._primary, query)
        if not results:
            # \u5907\u7528\u5f15\u64ce
            for name in self._engines:
                if name != self._primary:
                    results = self._fetch_engine(name, query)
                    if results:
                        break
        return results

    def search(self, keyword):
        return self.fetch_news([keyword])

    def quote(self, symbols): return []
    def kline(self, symbol, period="daily"): return []
    def finance(self, symbol): return {}
    def fund_flow(self, symbol): return {}
    def technical(self, symbol): return {}
