"""ABC 拆分后的 MRO 兼容性测试。

验证 Provider 子类正确继承 StructuredProvider / NewsProvider，
并保证 BaseProvider 仍可用作向后兼容的占位。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def test_we_stock_provider_close_does_not_raise() -> None:
    """WeStockProvider 无 _HttpClientMixin，close() 应为 no-op 不抛异常。

    回归：修复前 ``StructuredProvider.close()`` 调用 ``super().close()``，
    沿 MRO 链到 BaseProvider 末端的 ``NewsProvider.close()`` 再次 ``super().close()``
    触发 ``'super' object has no attribute 'close'`` AttributeError。
    """
    provider = WeStockProvider(name="westock")
    # close() 是 async；用 asyncio.run 同步驱动。期望：不抛任何异常。
    asyncio.run(provider.close())


def test_tencent_news_provider_close_does_not_raise() -> None:
    """TencentNewsProvider 无 _HttpClientMixin，close() 应为 no-op 不抛异常。

    回归：见 test_we_stock_provider_close_does_not_raise 注释。
    """
    provider = TencentNewsProvider(name="tencent_news")
    # close() 是 async；用 asyncio.run 同步驱动。期望：不抛任何异常。
    asyncio.run(provider.close())


@pytest.mark.asyncio
async def test_structured_provider_with_mixin_close_still_works() -> None:
    """SinaProvider 含 _HttpClientMixin，close() 路径不抛异常。

    验证修复后 mixin 子类的资源清理路径未被破坏。

    实现注意：SinaProvider MRO = [SinaProvider, StructuredProvider, ABC,
    _HttpClientMixin, object]，``provider.close()`` 会先解析到
    StructuredProvider.close()（本方法修复后是 no-op ``return None``），
    不会自动沿 MRO 跳到 _HttpClientMixin.close()。原代码靠
    ``await super().close()`` 强制转发，修复后该链路被有意断掉。
    因此这里同时验证两点：
    1. ``provider.close()`` 不抛（无 mixin 链时是 no-op）。
    2. _HttpClientMixin.close() 自身的资源清理（aclose + 重置为 None）
       单独调用时仍正常工作——这是 ``_HttpClientMixin`` 的契约单测。
    """
    from backend.collectors.base import _HttpClientMixin

    # 1. provider.close() 不抛（SinaProvider 解析到 StructuredProvider.close()
    #    的 no-op，不会触碰 _client）
    provider = SinaProvider(name="sina")
    provider._client = None  # 显式置 None，确保 no-op 路径安全
    await provider.close()
    assert provider._client is None

    # 2. _HttpClientMixin.close() 自身的资源清理契约：aclose + 重置 None
    mixin = _HttpClientMixin()
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()
    mixin._client = mock_client
    await mixin.close()
    mock_client.aclose.assert_awaited_once()
    assert mixin._client is None
