import sqlite3
import json
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.config import get_config
from backend.storage.database import get_db
from backend.utils import escape_like


class NewsService:

    def __init__(self, news_providers: list[BaseProvider] | None = None) -> None:
        if news_providers is not None:
            self._providers = news_providers
        else:
            config = get_config()
            providers_map = create_providers(config)
            self._providers = providers_map.get("news", [])

    async def collect_news(self) -> dict[str, int]:
        started_at = datetime.now(timezone.utc).isoformat()
        collected = 0
        skipped = 0
        all_items: list[dict] = []

        with get_db() as conn:
            tracked_symbol_rows = conn.execute(
                "SELECT symbol, name FROM tracked_assets WHERE enabled = 1"
            ).fetchall()
        tracked_symbols = [f"{r['name']}({r['symbol']})" for r in tracked_symbol_rows]

        for provider in self._providers:
            try:
                if hasattr(provider, "fetch_news"):
                    items = await provider.fetch_news(tracked_symbols)
                else:
                    items = await provider.search("")
                all_items.extend(items)
                logger.info("Provider {} 返回 {} 条新闻", provider.name, len(items))
            except Exception:
                logger.exception("Provider {} 采集新闻失败，跳过", provider.name)
                if provider.optional:
                    logger.warning("可选数据源 {} 不可用，静默跳过", provider.name)
                continue

        with get_db() as conn:
            tracked_assets_rows = conn.execute(
                "SELECT symbol, name, tags FROM tracked_assets WHERE enabled = 1"
            ).fetchall()

            affected_symbols_set: set[str] = set()

            # 预取最近一批已有 URL，避免逐条查询（N+1 问题）。
            # 仅取最近 5000 条以防止全表扫描导致内存膨胀；新增新闻的发布时间
            # 一定晚于这些记录，因此覆盖了实际去重需求。
            existing_urls: set[str] = set()
            url_rows = conn.execute(
                "SELECT url FROM news_items WHERE url IS NOT NULL "
                "ORDER BY id DESC LIMIT 5000"
            ).fetchall()
            existing_urls = {r["url"] for r in url_rows}

            for item in all_items:
                url = (item.get("url", "") or "").strip() or None
                if url and url in existing_urls:
                    skipped += 1
                    continue

                related_symbols = self._match_symbols_with_conn(
                    conn,
                    item.get("title", ""),
                    item.get("content"),
                    tracked_assets_rows,
                )
                for s in related_symbols:
                    affected_symbols_set.add(s)
                related_symbols_json = json.dumps(related_symbols, ensure_ascii=False)

                now = datetime.now(timezone.utc).isoformat()
                news_data = {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "url": url,
                    "content": item.get("content"),
                    "summary": item.get("summary"),
                    "published_at": item.get("published_at"),
                    "sentiment": item.get("sentiment", "neutral"),
                    "importance": item.get("importance", "normal"),
                    "related_symbols": related_symbols_json,
                    "collected_at": item.get("collected_at", now),
                }

                try:
                    conn.execute(
                        """INSERT INTO news_items
                           (title, source, url, content, summary, published_at,
                            sentiment, importance, related_symbols, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            news_data["title"],
                            news_data["source"],
                            news_data["url"],
                            news_data["content"],
                            news_data["summary"],
                            news_data["published_at"],
                            news_data["sentiment"],
                            news_data["importance"],
                            news_data["related_symbols"],
                            news_data["collected_at"],
                        ),
                    )
                    collected += 1
                    if url:
                        existing_urls.add(url)

                    if url:
                        raw_json = json.dumps(item, ensure_ascii=False, default=str)
                        conn.execute(
                            """INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            ("news", news_data["source"], "news", raw_json, now),
                        )
                except Exception:
                    logger.exception("新闻入库失败: title={}", news_data["title"])
                    skipped += 1

            finished_at = datetime.now(timezone.utc).isoformat()
            status = "success" if collected > 0 or skipped == 0 else "failure"
            error_message = None
            if collected == 0 and skipped > 0:
                error_message = "所有新闻均被跳过，无新增"

            try:
                conn.execute(
                    """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    ("news", status, started_at, finished_at, error_message, len(affected_symbols_set)),
                )
            except Exception:
                logger.exception("写入 run_logs 失败")

        logger.info("新闻采集完成: collected={}, skipped={}", collected, skipped)
        return {"collected": collected, "skipped": skipped}

    def _match_symbols_with_conn(self, conn: sqlite3.Connection, title: str, content: str | None = None, tracked_assets_rows: list | None = None) -> list[str]:
        if tracked_assets_rows is None:
            tracked_assets_rows = conn.execute(
                "SELECT symbol, name, tags FROM tracked_assets WHERE enabled = 1"
            ).fetchall()
        rows = tracked_assets_rows

        matched: list[str] = []
        text = title
        if content:
            text = f"{title} {content}"

        for row in rows:
            symbol: str = row["symbol"]
            name: str = row["name"] or ""
            tags_str: str | None = row["tags"]

            pattern = self._get_symbol_pattern(symbol)
            if pattern.search(text):
                matched.append(symbol)
                continue

            if name and name in text:
                matched.append(symbol)
                continue

            if tags_str:
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                for tag in tags:
                    if tag and tag in text:
                        matched.append(symbol)
                        break

        return matched

    def _get_symbol_pattern(self, symbol: str) -> re.Pattern:
        if not hasattr(self, "_symbol_patterns"):
            self._symbol_patterns: dict[str, re.Pattern] = {}
        pattern = self._symbol_patterns.get(symbol)
        if pattern is None:
            pattern = re.compile(
                r'(?<![a-zA-Z0-9])' + re.escape(symbol) + r'(?![a-zA-Z0-9])'
            )
            self._symbol_patterns[symbol] = pattern
        return pattern

    def _match_symbols(self, title: str, content: str | None = None) -> list[str]:
        with get_db() as conn:
            return self._match_symbols_with_conn(conn, title, content)

    def get_news(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []

        effective_filters = dict(filters) if filters else {}

        if "symbol" in effective_filters:
            conditions.append("related_symbols LIKE ? ESCAPE '\\'")
            params.append(f'%"%{escape_like(effective_filters["symbol"])}%"%')

        if "days" in effective_filters:
            conditions.append("published_at >= datetime('now', ?)")
            params.append(f'-{effective_filters["days"]} days')

        if "sentiment" in effective_filters:
            conditions.append("sentiment = ?")
            params.append(effective_filters["sentiment"])

        if "source" in effective_filters:
            conditions.append("source = ?")
            params.append(effective_filters["source"])

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        count_sql = f"SELECT COUNT(*) FROM news_items {where_clause}"
        data_sql = (
            f"SELECT * FROM news_items {where_clause} "
            "ORDER BY published_at IS NULL, published_at DESC "
            "LIMIT ? OFFSET ?"
        )

        with get_db() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
            rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["related_symbols"] = self._parse_related_symbols(item.get("related_symbols"))
            items.append(item)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "items": items,
            "page_info": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    def get_news_by_id(self, news_id: int) -> dict[str, Any] | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM news_items WHERE id = ?",
                (news_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["related_symbols"] = self._parse_related_symbols(result.get("related_symbols"))
            return result

    @staticmethod
    def _parse_related_symbols(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return []
        except (json.JSONDecodeError, TypeError):
            return []
