import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.collectors.base import BaseProvider
from backend.services.news_service import NewsService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


class FakeRSSProvider(BaseProvider):
    def __init__(self, name: str = "fake_rss", news_items: list[dict] | None = None) -> None:
        super().__init__(name=name)
        self._news_items = news_items or []

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
        return self._news_items


class FailingNeoDataProvider(BaseProvider):
    def __init__(self, name: str = "failing_neodata", optional: bool = True) -> None:
        super().__init__(name=name, optional=optional)

    async def search(self, keyword: str) -> list[dict]:
        raise ConnectionError("NeoData 服务不可用")

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


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


def _insert_asset(symbol: str, name: str, tags: str | None = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled, tags) VALUES (?, ?, ?, ?, 1, ?)",
            (symbol, name, symbol[:2], "stock", tags),
        )


def _make_news_item(
    title: str = "测试新闻",
    url: str = "https://example.com/news/1",
    source: str = "fake_rss",
    content: str | None = None,
    summary: str | None = None,
    published_at: str | None = None,
) -> dict:
    return {
        "title": title,
        "source": source,
        "url": url,
        "content": content,
        "summary": summary,
        "published_at": published_at or datetime.now(timezone.utc).isoformat(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


async def test_collect_news_success() -> None:
    news_items = [
        _make_news_item(title="市场大涨", url="https://example.com/1"),
        _make_news_item(title="科技股回调", url="https://example.com/2"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    result = await service.collect_news()
    assert result["collected"] == 2
    assert result["skipped"] == 0


async def test_collect_news_dedup_by_url() -> None:
    news_items = [
        _make_news_item(title="市场大涨", url="https://example.com/dup"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])

    result1 = await service.collect_news()
    assert result1["collected"] == 1
    assert result1["skipped"] == 0

    result2 = await service.collect_news()
    assert result2["collected"] == 0
    assert result2["skipped"] == 1


async def test_collect_news_match_symbol_by_name() -> None:
    _insert_asset("hk00700", "腾讯控股")
    news_items = [
        _make_news_item(title="腾讯控股发布Q1财报", url="https://example.com/tencent"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    await service.collect_news()

    with get_db() as conn:
        row = conn.execute("SELECT related_symbols FROM news_items WHERE url = ?", ("https://example.com/tencent",)).fetchone()
    assert row is not None
    symbols = json.loads(row["related_symbols"])
    assert "hk00700" in symbols


async def test_collect_news_match_multiple_symbols() -> None:
    _insert_asset("hk00700", "腾讯控股")
    _insert_asset("sh600519", "贵州茅台")
    news_items = [
        _make_news_item(
            title="腾讯控股与贵州茅台同日发布财报",
            url="https://example.com/multi",
        ),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    await service.collect_news()

    with get_db() as conn:
        row = conn.execute("SELECT related_symbols FROM news_items WHERE url = ?", ("https://example.com/multi",)).fetchone()
    assert row is not None
    symbols = json.loads(row["related_symbols"])
    assert "hk00700" in symbols
    assert "sh600519" in symbols


async def test_collect_news_neodata_fallback_to_rss() -> None:
    rss_items = [
        _make_news_item(title="RSS新闻", url="https://example.com/rss-only"),
    ]
    failing_neodata = FailingNeoDataProvider(name="neodata", optional=True)
    rss_provider = FakeRSSProvider(name="sina_rss", news_items=rss_items)
    service = NewsService(news_providers=[failing_neodata, rss_provider])

    result = await service.collect_news()
    assert result["collected"] == 1
    assert result["skipped"] == 0


async def test_collect_news_neodata_failure_no_crash() -> None:
    failing_neodata = FailingNeoDataProvider(name="neodata", optional=True)
    service = NewsService(news_providers=[failing_neodata])
    result = await service.collect_news()
    assert result["collected"] == 0


async def test_get_news_pagination() -> None:
    for i in range(5):
        with get_db() as conn:
            conn.execute(
                """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"新闻{i}",
                    "test",
                    f"https://example.com/page/{i}",
                    datetime.now(timezone.utc).isoformat(),
                    "neutral",
                    "normal",
                    "[]",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    service = NewsService(news_providers=[])
    result = service.get_news(page=1, page_size=2)
    assert len(result["items"]) == 2
    assert result["page_info"]["total"] == 5
    assert result["page_info"]["total_pages"] == 3


async def test_get_news_filter_by_symbol() -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "腾讯新闻",
                "test",
                "https://example.com/filter1",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                json.dumps(["hk00700"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "茅台新闻",
                "test",
                "https://example.com/filter2",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                json.dumps(["sh600519"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    service = NewsService(news_providers=[])
    result = service.get_news(filters={"symbol": "hk00700"})
    assert len(result["items"]) == 1
    assert result["items"][0]["related_symbols"] == ["hk00700"]


async def test_get_news_filter_by_sentiment() -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "正面新闻",
                "test",
                "https://example.com/sent1",
                datetime.now(timezone.utc).isoformat(),
                "positive",
                "normal",
                "[]",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "中性新闻",
                "test",
                "https://example.com/sent2",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                "[]",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    service = NewsService(news_providers=[])
    result = service.get_news(filters={"sentiment": "positive"})
    assert len(result["items"]) == 1
    assert result["items"][0]["sentiment"] == "positive"


async def test_get_news_filter_by_source() -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "新浪新闻",
                "sina_rss",
                "https://example.com/src1",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                "[]",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            """INSERT INTO news_items (title, source, url, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "其他新闻",
                "other",
                "https://example.com/src2",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                "[]",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    service = NewsService(news_providers=[])
    result = service.get_news(filters={"source": "sina_rss"})
    assert len(result["items"]) == 1
    assert result["items"][0]["source"] == "sina_rss"


async def test_get_news_by_id() -> None:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO news_items (title, source, url, content, published_at, sentiment, importance, related_symbols, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "详细新闻",
                "test",
                "https://example.com/detail",
                "这是完整的新闻正文内容",
                datetime.now(timezone.utc).isoformat(),
                "neutral",
                "normal",
                json.dumps(["hk00700"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        news_id = cursor.lastrowid

    service = NewsService(news_providers=[])
    result = service.get_news_by_id(news_id)
    assert result is not None
    assert result["title"] == "详细新闻"
    assert result["content"] == "这是完整的新闻正文内容"
    assert result["related_symbols"] == ["hk00700"]


async def test_get_news_by_id_not_found() -> None:
    service = NewsService(news_providers=[])
    result = service.get_news_by_id(999)
    assert result is None


async def test_get_news_empty() -> None:
    service = NewsService(news_providers=[])
    result = service.get_news()
    assert result["items"] == []
    assert result["page_info"]["total"] == 0


async def test_collect_news_run_logs() -> None:
    news_items = [
        _make_news_item(title="日志测试新闻", url="https://example.com/log"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    await service.collect_news()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM run_logs WHERE task_name = 'news' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row is not None
    assert row["task_name"] == "news"
    assert row["status"] == "success"
    assert row["affected_assets"] == 0  # N-13: unique symbols affected, not news count
    assert row["started_at"] is not None
    assert row["finished_at"] is not None


async def test_match_symbols_by_symbol_code() -> None:
    _insert_asset("hk00700", "腾讯控股")
    service = NewsService(news_providers=[])
    matched = service._match_symbols("hk00700 发布财报")
    assert "hk00700" in matched


async def test_match_symbols_by_tags() -> None:
    _insert_asset("hk00700", "腾讯控股", tags="互联网,AI概念")
    service = NewsService(news_providers=[])
    matched = service._match_symbols("AI概念板块大涨")
    assert "hk00700" in matched


async def test_match_symbols_by_content() -> None:
    _insert_asset("hk00700", "腾讯控股")
    service = NewsService(news_providers=[])
    matched = service._match_symbols("市场动态", content="腾讯控股今日表现亮眼")
    assert "hk00700" in matched


async def test_collect_news_default_sentiment_and_importance() -> None:
    news_items = [
        _make_news_item(title="默认值测试", url="https://example.com/default"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    await service.collect_news()

    with get_db() as conn:
        row = conn.execute("SELECT sentiment, importance FROM news_items WHERE url = ?", ("https://example.com/default",)).fetchone()
    assert row is not None
    assert row["sentiment"] == "neutral"
    assert row["importance"] == "normal"


async def test_collect_news_raw_data_saved() -> None:
    news_items = [
        _make_news_item(title="原始数据测试", url="https://example.com/raw"),
    ]
    provider = FakeRSSProvider(name="fake_rss", news_items=news_items)
    service = NewsService(news_providers=[provider])
    await service.collect_news()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM raw_data WHERE data_type = 'news' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["source"] == "fake_rss"
    raw = json.loads(row["raw_json"])
    assert raw["title"] == "原始数据测试"


async def test_evidence_builder_news_fields_consumable_by_ai_analyzer_via_aget_db(tmp_path: Path) -> None:
    """验证 EvidenceBuilder 通过 aget_db (aiosqlite) 路径构建 news 字段名与 ai_analyzer 期望一致。"""
    from backend.services.evidence_builder import EvidenceBuilder
    from backend.services.ai_analyzer import AIAnalyzer
    from backend.storage.database import set_db_path as set_db, aget_db as aget
    from backend.storage.schema import init_db_sync

    db_path = str(tmp_path / "test.db")
    set_db(db_path)
    init_db_sync()

    # 插入已追踪标的
    async with aget() as conn:
        await conn.execute(
            "INSERT INTO tracked_assets (symbol, name, market, asset_type, enabled) VALUES (?, ?, ?, ?, 1)",
            ("hk00700", "腾讯控股", "hk", "stock"),
        )

    # 插入不同情感的新闻数据
    sentiments = ["positive", "positive", "positive", "positive", "negative", "neutral"]
    async with aget() as conn:
        for i, sentiment in enumerate(sentiments):
            await conn.execute(
                """INSERT INTO news_items (title, source, url, sentiment, importance,
                   related_symbols, published_at, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"测试新闻 {i}",
                    "test_rss",
                    f"https://example.com/news/{i}",
                    sentiment,
                    "normal",
                    json.dumps(["hk00700"]),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    # 通过 EvidenceBuilder 构建 news 数据
    evidence = await EvidenceBuilder.build("hk00700")
    news_data = evidence["news"]

    assert news_data is not None
    # 验证字段名与 ai_analyzer 期望一致
    assert "total_count" in news_data, "缺少 total_count 字段"
    assert "positive_count" in news_data, "缺少 positive_count 字段"
    assert "negative_count" in news_data, "缺少 negative_count 字段"
    assert "latest" in news_data, "缺少 latest 字段"

    # 验证 ai_analyzer 可以正确消费 evidence_builder 的输出（不报错且返回有效结果）
    result = AIAnalyzer.analyze(evidence)
    assert isinstance(result, dict)
    assert "action" in result
    assert "confidence" in result

    set_db(None)


async def test_collect_news_acquires_write_lock() -> None:
    """验证 collect_news 写块持有 _WRITE_LOCK。

    threading.Lock 是 C 实现,属性只读;用 ObservableLock 包装验证。
    news_service 顶部 from ... import _WRITE_LOCK 绑定本地引用,
    必须同时 patch 两边。
    """
    import threading
    from unittest.mock import patch
    from backend.services import collection_service
    import backend.services.news_service as ns_mod

    items = [
        {
            "title": "锁测试",
            "url": "https://example.com/lock-test",
            "source": "fake",
        }
    ]
    provider = FakeRSSProvider(name="fake_rss_lock", news_items=items)
    service = NewsService(news_providers=[provider])

    original = collection_service._WRITE_LOCK
    observed_held: list[bool] = []

    class _ObservableLock:
        def __init__(self, inner: threading.Lock) -> None:
            self._inner = inner

        def __enter__(self) -> "_ObservableLock":
            self._inner.__enter__()
            observed_held.append(self._inner.locked())
            return self

        def __exit__(self, *args) -> None:
            self._inner.__exit__(*args)

    observable = _ObservableLock(original)
    with patch.object(collection_service, "_WRITE_LOCK", new=observable), \
         patch.object(ns_mod, "_WRITE_LOCK", new=observable):
        await service.collect_news()

    assert observed_held, "collect_news 未进入 _WRITE_LOCK 上下文"
    assert observed_held[0] is True, "collect_news 进入 _WRITE_LOCK 时锁未持有"


async def test_collect_news_duplicate_url_uses_or_ignore() -> None:
    """验证 INSERT OR IGNORE 在 DB 层兜底去重。"""
    items = [
        {
            "title": "重复URL测试",
            "url": "https://example.com/dup-test",
            "source": "fake",
        }
    ]
    provider = FakeRSSProvider(name="fake_rss_dup", news_items=items)
    service = NewsService(news_providers=[provider])

    # 第一次收集
    r1: dict = await service.collect_news()
    assert r1["collected"] == 1
    assert r1["skipped"] == 0

    # 第二次收集,相同 URL 应被 DB 层 partial unique index 拦截
    r2: dict = await service.collect_news()
    assert r2["collected"] == 0
    assert r2["skipped"] >= 1


async def test_tag_patterns_cache_key_stable() -> None:
    """验证缓存 key 是 (symbol, tags_str) tuple,多次调用只编译一次。"""
    service = NewsService(news_providers=[])

    # 模拟 sqlite3.Row
    class FakeRow:
        def __init__(self, symbol: str) -> None:
            self._symbol = symbol

        def keys(self) -> list[str]:
            return ["symbol"]

        def __getitem__(self, key: str) -> str:
            if key == "symbol":
                return self._symbol
            raise KeyError(key)

    row = FakeRow("hk00700")
    p1 = service._get_tag_patterns(row, "AI,云")
    p2 = service._get_tag_patterns(row, "AI,云")
    # 同一 key 命中缓存,返回同一对象
    assert p1 is p2
    assert ("hk00700", "AI,云") in service._tag_patterns_cache
    # 不同 tags_str 不同 key
    p3 = service._get_tag_patterns(row, "新能源")
    assert p3 is not p1
    assert ("hk00700", "新能源") in service._tag_patterns_cache
