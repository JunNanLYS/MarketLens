"""腾讯新闻 HTTP 提供者。

通过腾讯新闻公开的热榜 API 获取热点新闻，无需 API Key。
API: https://r.inews.qq.com/gw/event/hot_ranking_list
"""

import json
from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import BaseProvider


class TencentNewsHTTPProvider(BaseProvider):
    """腾讯新闻热榜提供者，使用公开 HTTP API 获取热点新闻（无需 API Key）。"""

    _API_URL: str = "https://r.inews.qq.com/gw/event/hot_ranking_list"

    def __init__(
        self,
        name: str,
        timeout: int = 15,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self.max_items: int = int(params.get("max_items", 50)) if params else 50

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
        try:
            resp = httpx.get(
                self._API_URL,
                params={"page_size": self.max_items},
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            return self._parse_response(resp.json())
        except httpx.TimeoutException:
            logger.warning("TencentNews HTTP 请求超时: timeout={}s", self.timeout)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("TencentNews HTTP 错误: status={}", e.response.status_code)
            return []
        except Exception as e:
            logger.error("TencentNews HTTP 请求异常: error={}", e)
            return []

    def _parse_response(self, data: dict) -> list[dict]:
        if data.get("ret") != 0:
            logger.warning("TencentNews API 返回非零 ret: {}", data.get("ret"))
            return []

        results: list[dict] = []
        seen: set[str] = set()

        idlist = data.get("idlist", [])
        if not isinstance(idlist, list):
            idlist = []

        for event_group in idlist:
            newslist = event_group.get("newslist", [])
            if not isinstance(newslist, list):
                continue

            for item in newslist:
                if not isinstance(item, dict):
                    continue

                # 跳过占位/引导条目
                articletype = item.get("articletype", "0")
                if articletype == "560":
                    continue

                title = item.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)

                url = item.get("url") or item.get("surl") or None
                abstract = item.get("abstract") or item.get("nlpAbstract") or ""
                source = item.get("source") or item.get("chlname") or "腾讯新闻"

                # 发布时间
                ts = item.get("timestamp")
                published_at = None
                if ts:
                    try:
                        published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass
                if not published_at:
                    published_at = item.get("time")

                # 重要性：基于热榜排名
                hot_event = item.get("hotEvent", {})
                ranking = hot_event.get("ranking") or item.get("ranking", 99)
                hot_score = hot_event.get("hotScore", 0)
                try:
                    ranking = int(ranking)
                except (ValueError, TypeError):
                    ranking = 99

                if ranking <= 3:
                    importance = "high"
                elif ranking <= 10:
                    importance = "normal"
                else:
                    importance = "low"

                results.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "content": abstract,
                    "summary": abstract,
                    "published_at": published_at,
                    "sentiment": "neutral",
                    "importance": importance,
                    "collected_at": self._now(),
                })

                if len(results) >= self.max_items:
                    break

            if len(results) >= self.max_items:
                break

        logger.info("TencentNews HTTP 获取 {} 条新闻: provider={}", len(results), self.name)
        return results
