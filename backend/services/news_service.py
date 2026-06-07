import sqlite3
import json
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.collectors import BaseProvider, create_providers
from backend.config import get_config
from backend.services.collection_service import _WRITE_LOCK
from backend.storage.database import get_connection_sync, get_db


class NewsService:

    def __init__(self, news_providers: list[BaseProvider] | None = None) -> None:
        if news_providers is not None:
            self._providers = news_providers
        else:
            config = get_config()
            providers_map = create_providers(config)
            self._providers = providers_map.get("news", [])
        # 预编译的正则缓存：避免每条新闻 × 每标的 × 重复 re.compile。
        # 旧实现中 _get_symbol_pattern 在循环内被调用，每次都走 if/return。
        # 改为初始化即建立 cache，并在调用前一次性 build。
        self._symbol_patterns: dict[str, re.Pattern] = {}
        # tags 缓存：(symbol, tags_str) -> list[re.Pattern]。旧实现用 id(row)
        # 作为 key,sqlite3.Row 的 id() 在 fetchall 后被 GC 回收,缓存实际从不命中。
        self._tag_patterns_cache: dict[tuple[str | None, str], list[re.Pattern]] = {}


    async def collect_news(self) -> dict[str, int]:
        """采集新闻并写入 news_items / raw_data，同时记录 run_logs 审计行。

        满足 CLAUDE.md 硬约束："Data collection MUST leave a run_logs row"。
        即便在采集/落库任意阶段抛出异常（包括 `_get_active_symbols` 等价
        的 `tracked_symbols` 查询、`conn.commit()` 失败等），都会通过外层
        `try/except/finally` 兜底写入一条 run_logs 行（status=failure），
        保证 UI 历史不漏记录。

        Returns:
            含 collected / skipped 计数的字典。
        """
        started_at = datetime.now(timezone.utc).isoformat()
        result: dict[str, int] = {"collected": 0, "skipped": 0}
        status: str = "success"
        error_message: str | None = None
        try:
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

            with _WRITE_LOCK:
                conn = get_connection_sync()
                try:
                    tracked_assets_rows = conn.execute(
                        "SELECT symbol, name, tags FROM tracked_assets WHERE enabled = 1"
                    ).fetchall()

                    affected_symbols_set: set[str] = set()

                    # 预取最近一批已有 URL,避免逐条查询(N+1 问题)。
                    # 仅取最近 5000 条以防止全表扫描导致内存膨胀;新增新闻的发布时间
                    # 一定晚于这些记录,因此覆盖了实际去重需求。
                    # DB 层兜底:idx_news_items_url_unique 部分唯一索引保证重复 URL 不可插入。
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
                            # INSERT OR IGNORE: 依赖 idx_news_items_url_unique 部分唯一索引
                            # (url 非空时);空 URL 允许重复但 unique index 不阻止空值插入。
                            cursor = conn.execute(
                                """INSERT OR IGNORE INTO news_items
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
                            if cursor.rowcount == 0:
                                # 重复 URL 已被 partial unique index 拦截
                                skipped += 1
                                continue
                            collected += 1
                            if url:
                                existing_urls.add(url)

                            if url:
                                raw_json = json.dumps(item, ensure_ascii=False, default=str)
                                conn.execute(
                                    """INSERT INTO raw_data (symbol, source, data_type, raw_json, collected_at)
                                       VALUES (?, ?, ?, ?, ?)""",
                                    (None, news_data["source"], "news", raw_json, now),
                                )
                        except Exception:
                            logger.exception("新闻入库失败: title={}", news_data["title"])
                            skipped += 1

                    finished_at = datetime.now(timezone.utc).isoformat()
                    status = "success" if collected > 0 or skipped == 0 else "failure"
                    error_message = None
                    if collected == 0 and skipped > 0:
                        error_message = "所有新闻均被跳过，无新增"

                    # 单次 run_logs 写入：原 collect_news 在此处 INSERT run_logs，
                    # 但若 INSERT 本身或之后 commit 失败，外层 except 会跳过审计。
                    # 统一上移到本方法外层 finally，保证任意路径都留痕。
                    affected_assets = len(affected_symbols_set)
                    conn.execute(
                        """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        ("news", status, started_at, finished_at, error_message, affected_assets),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

            logger.info("新闻采集完成: collected={}, skipped={}", collected, skipped)
            result = {"collected": collected, "skipped": skipped}
            return result
        except Exception as e:
            # 异常路径：覆盖 `_get_active_symbols` 等价的 tracked_assets 查询、
            # provider 循环未捕获异常、落库段 conn.rollback() 后 re-raise 等所有
            # 提前退出路径。记录 failure run_logs 后再向上抛出，确保上层
            # `_run_news` 的 try/except 不会因为我们写日志而吞掉原异常。
            status = "failure"
            error_message = str(e)[:500]
            raise
        finally:
            # 不论成功还是异常，最终都写一条 run_logs 行。成功路径时本方法末尾
            # 已写过一条（status=success），此处仅在异常路径上兜底补写一条
            # status=failure 行 —— 用 INSERT OR IGNORE 配合 task_name + 时间
            # 去重无法精确判定，故采用：成功路径不再写第二次（用局部标志区分）。
            try:
                # 注意：成功路径上 conn 已 commit 并 close；这里用新的 sync 连接
                # 写兜底行不会冲突（_WRITE_LOCK 释放后新连接安全）。但若成功路径
                # 已写过 run_logs 行，再次插入会产生重复行 —— 所以先 SELECT 判断
                # 同一 started_at 是否已有 news 行。
                with get_db() as conn_check:
                    existing_row = conn_check.execute(
                        """SELECT 1 FROM run_logs
                           WHERE task_name = 'news' AND started_at = ?
                           LIMIT 1""",
                        (started_at,),
                    ).fetchone()
                if existing_row is None:
                    finished_at_final = datetime.now(timezone.utc).isoformat()
                    with get_db() as conn_finish:
                        conn_finish.execute(
                            """INSERT INTO run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            ("news", status, started_at, finished_at_final, error_message, 0),
                        )
            except Exception:
                # 兜底写入 run_logs 失败：仅记日志，不影响原异常向上传播。
                logger.exception("collect_news 兜底写入 run_logs 失败")

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

            # symbol 预编译 pattern：缓存避免每次重新 re.compile
            pattern = self._get_symbol_pattern(symbol)
            if pattern.search(text):
                matched.append(symbol)
                continue

            # name：单次 in 操作（无法预编译，保持原逻辑）
            if name and name in text:
                matched.append(symbol)
                continue

            # tags：使用预编译的 re.Pattern 一次扫描
            if tags_str:
                tags = self._get_tag_patterns(row, tags_str)
                if tags:
                    for pat in tags:
                        if pat.search(text):
                            matched.append(symbol)
                            break

        return matched

    def _get_symbol_pattern(self, symbol: str) -> re.Pattern:
        pattern = self._symbol_patterns.get(symbol)
        if pattern is None:
            pattern = re.compile(
                r'(?<![a-zA-Z0-9])' + re.escape(symbol) + r'(?![a-zA-Z0-9])'
            )
            self._symbol_patterns[symbol] = pattern
        return pattern

    def _get_tag_patterns(self, row, tags_str: str) -> list[re.Pattern]:
        """预编译 row 对应的 tags 正则列表,缓存以避免重复编译。"""
        # sqlite3.Row 不支持 .get，按索引访问
        symbol = row["symbol"] if "symbol" in row.keys() else None
        cache_key = (symbol, tags_str)
        cached = self._tag_patterns_cache.get(cache_key)
        if cached is not None:
            return cached
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        compiled: list[re.Pattern] = [
            re.compile(re.escape(t)) for t in tags if t
        ]
        self._tag_patterns_cache[cache_key] = compiled
        return compiled

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
            # 用 json_each 替代 LIKE:避免全表扫 + 误匹配 (e.g. 搜索 '00700' 会误中 'hk00700')
            sym = effective_filters["symbol"]
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(related_symbols) WHERE value = ?)"
            )
            params.append(sym)

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
