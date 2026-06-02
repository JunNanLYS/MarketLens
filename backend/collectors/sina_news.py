"""新浪财经新闻 JSON API 提供者。

通过新浪财经 roll API 获取最新财经新闻，返回结构化的 JSON 数据。
"""

import json
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class SinaNewsProvider(BaseProvider):
    """新浪财经新闻提供者，使用 JSON API 获取财经新闻。"""

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
            logger.warning("新浪新闻 URL 未配置: provider={}", self.name)
            return []
        try:
            resp = httpx.get(
                self.url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://finance.sina.com.cn",
                },
            )
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
