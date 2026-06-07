from datetime import datetime, timezone

import httpx
from loguru import logger

from backend.collectors.base import NewsProvider, _HttpClientMixin


class TencentNewsHTTPProvider(NewsProvider, _HttpClientMixin):
    """腾讯新闻热榜提供者，使用公开 HTTP API 获取热点新闻（异步版）。"""

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
        # 懒加载 httpx.AsyncClient：见 _HttpClientMixin 注释
        self._client: httpx.AsyncClient | None = None
        self._client_headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

    def _client_kwargs(self) -> dict:
        """覆写 mixin 钩子，注入 headers + follow_redirects。"""
        return {
            "timeout": httpx.Timeout(self.timeout),
            "follow_redirects": True,
            "headers": self._client_headers,
        }


    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        try:
            client = await self._get_client()
            resp = await client.get(
                self._API_URL,
                params={"page_size": self.max_items},
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

                ts = item.get("timestamp")
                published_at = None
                if ts:
                    try:
                        published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass
                if not published_at:
                    published_at = item.get("time")

                hot_event = item.get("hotEvent", {})
                ranking = hot_event.get("ranking") or item.get("ranking", 99)
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
