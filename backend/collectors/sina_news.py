import json
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class SinaNewsProvider(BaseProvider):
    """新浪财经新闻 JSON API 提供者（异步版）。"""

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.url: str = self.params.get("url", "")
        self.max_items: int = int(self.params.get("max_items", 50))
        # 懒加载 httpx.AsyncClient：见 rss.py 同类注释
        self._client: httpx.AsyncClient | None = None
        self._client_headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """首次使用时创建 httpx 客户端，后续复用。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers=self._client_headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


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

    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        if not self.url:
            logger.warning("新浪新闻 URL 未配置: provider={}", self.name)
            return []
        try:
            client = await self._get_client()
            resp = await client.get(self.url)
            resp.raise_for_status()
            return self._parse_json(resp.json())
        except httpx.TimeoutException:
            logger.warning("新浪新闻请求超时: url={}, timeout={}s", self.url, self.timeout)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("新浪新闻 HTTP 错误: url={}, status={}", self.url, e.response.status_code)
            return []
        except Exception as e:
            logger.error("新浪新闻请求异常: url={}, error={}", self.url, e)
            return []

    def _parse_json(self, data: dict) -> list[dict]:
        results: list[dict] = []
        try:
            news_list = data.get("result", {}).get("data", [])
        except (KeyError, TypeError, AttributeError) as e:
            logger.error("新浪新闻 JSON 解析失败: provider={}, error={}", self.name, e)
            return []

        if not isinstance(news_list, list):
            logger.warning("新浪新闻 data 字段非列表: provider={}, type={}", self.name, type(news_list))
            return []

        for item in news_list[:self.max_items]:
            try:
                title = item.get("title", "").strip()
                if not title:
                    continue
                url = item.get("url", "") or item.get("wapurl", "")
                intro = item.get("intro", "").strip()
                ctime = item.get("ctime", "")
                published_at = None
                if ctime:
                    try:
                        published_at = datetime.fromtimestamp(int(ctime), tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        published_at = ctime

                results.append({
                    "title": title,
                    "source": item.get("media_name", "") or "新浪财经",
                    "url": url or None,
                    "content": intro,
                    "summary": intro,
                    "published_at": published_at,
                    "sentiment": "neutral",
                    "importance": "normal",
                    "collected_at": self._now(),
                })
            except Exception as e:
                logger.warning("新浪新闻条目解析失败: provider={}, error={}", self.name, e)
                continue

        logger.info("新浪新闻获取 {} 条: provider={}", len(results), self.name)
        return results
