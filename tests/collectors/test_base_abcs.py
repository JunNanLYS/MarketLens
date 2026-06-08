"""ABC 拆分后的 MRO 兼容性测试。

验证 Provider 子类正确继承 StructuredProvider / NewsProvider，
并保证 BaseProvider 仍可用作向后兼容的占位。
"""

from __future__ import annotations

from backend.collectors.base import BaseProvider, NewsProvider, StructuredProvider
from backend.collectors.neodata import NeoDataProvider
from backend.collectors.rss import RSSProvider
from backend.collectors.search_engine import SearchEngineNewsProvider
from backend.collectors.sina import SinaProvider
from backend.collectors.sina_news import SinaNewsProvider
from backend.collectors.tencent_news import TencentNewsProvider
from backend.collectors.tencent_news_http import TencentNewsHTTPProvider
from backend.collectors.westock import WeStockProvider


def test_westock_inherits_both_abcs() -> None:
    """WeStockProvider 既有 6 数据方法又有 fetch_news → 视为双类型。"""
    p = WeStockProvider(name="westock")
    assert isinstance(p, StructuredProvider)
    assert isinstance(p, NewsProvider)
    assert isinstance(p, BaseProvider)  # 向后兼容


def test_neodata_inherits_both_abcs() -> None:
    """NeoDataProvider 同样提供结构化 + 新闻 → 双类型。"""
    p = NeoDataProvider(name="neodata")
    assert isinstance(p, StructuredProvider)
    assert isinstance(p, NewsProvider)
    assert isinstance(p, BaseProvider)


def test_sina_inherits_only_structured() -> None:
    """SinaProvider 纯结构化数据源。"""
    p = SinaProvider(name="sina")
    assert isinstance(p, StructuredProvider)
    assert not isinstance(p, NewsProvider)


def test_rss_inherits_only_news() -> None:
    """RSSProvider 纯新闻源。"""
    p = RSSProvider(name="bbc", params={"url": "https://example.com/rss"})
    assert isinstance(p, NewsProvider)
    assert not isinstance(p, StructuredProvider)


def test_sina_news_inherits_only_news() -> None:
    """SinaNewsProvider 纯新闻源。"""
    p = SinaNewsProvider(name="sina_news")
    assert isinstance(p, NewsProvider)
    assert not isinstance(p, StructuredProvider)


def test_tencent_news_inherits_only_news() -> None:
    """TencentNewsProvider 纯新闻源。"""
    p = TencentNewsProvider(name="tencent_news")
    assert isinstance(p, NewsProvider)
    assert not isinstance(p, StructuredProvider)


def test_tencent_news_http_inherits_only_news() -> None:
    """TencentNewsHTTPProvider 纯新闻源。"""
    p = TencentNewsHTTPProvider(name="tencent_news_http")
    assert isinstance(p, NewsProvider)
    assert not isinstance(p, StructuredProvider)


def test_search_engine_inherits_only_news() -> None:
    """SearchEngineNewsProvider 纯新闻源（search() 委托给 fetch_news）。"""
    p = SearchEngineNewsProvider(name="bing", params={"primary": "bing"})
    assert isinstance(p, NewsProvider)
    assert not isinstance(p, StructuredProvider)


def test_baseprovider_mro_contains_both_abcs() -> None:
    """BaseProvider 自身必须同时是 StructuredProvider 与 NewsProvider 子类。"""
    assert issubclass(BaseProvider, StructuredProvider)
    assert issubclass(BaseProvider, NewsProvider)


def test_westock_mro_contains_both_abcs() -> None:
    """MRO 中应同时出现 StructuredProvider 与 NewsProvider。"""
    mro_names = {c.__name__ for c in WeStockProvider.__mro__}
    assert "StructuredProvider" in mro_names
    assert "NewsProvider" in mro_names


def test_news_only_provider_has_no_structured_methods() -> None:
    """纯 NewsProvider 不应再携带 6 个 structured 数据的 stub 方法。

    抽离 ABC 后这些 stub 已从子类删除；ABC 本身仍提供空默认实现，
    但子类应不再显式声明（用 'search' in RSSProvider.__dict__ 检查）。
    """
    for cls in (RSSProvider, SinaNewsProvider, TencentNewsHTTPProvider):
        assert "quote" not in cls.__dict__, f"{cls.__name__} 不应再声明 quote()"
        assert "kline" not in cls.__dict__, f"{cls.__name__} 不应再声明 kline()"
        assert "finance" not in cls.__dict__, f"{cls.__name__} 不应再声明 finance()"
        assert "fund_flow" not in cls.__dict__, f"{cls.__name__} 不应再声明 fund_flow()"
        assert "technical" not in cls.__dict__, f"{cls.__name__} 不应再声明 technical()"
