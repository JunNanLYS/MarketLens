"""news_items schema 迁移测试：confidence + sentiment_reason 列添加幂等性。"""

import sqlite3

import pytest

from backend.storage.schema import (
    _migrate_news_items_add_confidence_reason_sync,
    _news_items_has_confidence_sync,
    _news_items_has_sentiment_reason_sync,
)


@pytest.fixture
def isolated_conn() -> sqlite3.Connection:
    """每个测试一个独立内存 DB,避免污染共享 sqlite。

    news_items 表只放不含 confidence/sentiment_reason 列的旧版 DDL,
    迁移函数应当能成功追加两列。
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT,
            content TEXT,
            summary TEXT,
            published_at TIMESTAMP,
            sentiment TEXT,
            sectors TEXT,
            importance TEXT,
            related_symbols TEXT,
            collected_at TIMESTAMP NOT NULL
        )"""
    )
    conn.commit()
    yield conn
    conn.close()


def test_migrate_adds_confidence_column(isolated_conn: sqlite3.Connection) -> None:
    """迁移应当同时追加 confidence 和 sentiment_reason 两列。"""
    conn = isolated_conn
    # 迁移前不存在两列
    assert not _news_items_has_confidence_sync(conn)
    assert not _news_items_has_sentiment_reason_sync(conn)

    _migrate_news_items_add_confidence_reason_sync(conn)

    # 迁移后两列均存在
    assert _news_items_has_confidence_sync(conn)
    assert _news_items_has_sentiment_reason_sync(conn)

    # 表结构应当包含这两列
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(news_items)").fetchall()
    }
    assert "confidence" in columns
    assert "sentiment_reason" in columns


def test_migrate_idempotent(isolated_conn: sqlite3.Connection) -> None:
    """第二次调用迁移函数不应报错(列已存在,跳过)。"""
    conn = isolated_conn
    _migrate_news_items_add_confidence_reason_sync(conn)
    # 第一次迁移后两列已存在
    assert _news_items_has_confidence_sync(conn)
    assert _news_items_has_sentiment_reason_sync(conn)

    # 第二次调用不报错(幂等)
    _migrate_news_items_add_confidence_reason_sync(conn)

    # 两列仍然存在
    assert _news_items_has_confidence_sync(conn)
    assert _news_items_has_sentiment_reason_sync(conn)
