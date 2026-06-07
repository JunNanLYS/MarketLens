"""数据采集提供者抽象基类（异步版）。

本模块将原 BaseProvider 拆分为两个独立的 ABC：
- StructuredProvider：结构化数据（行情/K线/财务/资金流向/技术指标）
- NewsProvider：新闻数据（fetch_news）

子类应按需选择继承；少数既提供结构化数据又提供新闻的 Provider
（如 WeStockProvider、NeoDataProvider）需双继承。

BaseProvider 保留为（StructuredProvider, NewsProvider）的多继承占位，
旧代码 / 外部代码可继续继承以保持向后兼容。

注意：6 个数据方法（search/quote/kline/finance/fund_flow/technical）保留
与旧版相同的"空默认实现"语义（不抛 NotImplementedError），保证：
- 旧 Provider 子类迁移到新 ABC 后，行为不变；
- 旧代码中 `isinstance(p, BaseProvider)` 检查依旧成立；
- 任何缺方法的子类不会因 ABC 检查失败而无法实例化。

_HttpClientMixin：httpx.AsyncClient 懒加载 + close 公共逻辑。
子类覆写 _client_kwargs() 即可注入 headers/follow_redirects 等自定义参数。
"""
from abc import ABC

import httpx


class _HttpClientMixin:
    """HTTP 客户端懒加载 + close 公共 mixin。

    设计要点：
    1. 懒加载：`__init__` 不创建 client，避免 Windows + Python 3.13 上
       SSL/连接池初始化阻塞 3.8s+。
    2. 单例复用：首次 await 时创建，后续复用同一 client。
    3. close 幂等：重复 close 安全，重置 _client 为 None。
    4. 子类定制：覆写 _client_kwargs() 返回 httpx.AsyncClient 构造 kwargs，
       不覆写 _get_client / close。

    调用约定：子类业务方法统一使用 `await self._get_client()`，
    与原 BaseProvider 提供的 async 接口保持一致。
    """

    _client: httpx.AsyncClient | None = None

    def _client_kwargs(self) -> dict:
        """返回 httpx.AsyncClient 构造 kwargs。子类可覆写以注入 headers 等。"""
        return {"timeout": self.timeout}  # type: ignore[attr-defined]

    async def _get_client(self) -> httpx.AsyncClient:
        """首次使用时创建 httpx 客户端，后续复用。"""
        if not hasattr(self, "_client") or self._client is None:
            self._client = httpx.AsyncClient(**self._client_kwargs())
        return self._client

    async def close(self) -> None:
        """关闭底层 httpx 客户端，重置为 None。幂等。"""
        if getattr(self, "_client", None) is not None:
            await self._client.aclose()
            self._client = None


class StructuredProvider(ABC):
    """结构化数据采集提供者（行情/K线/财务/资金流向/技术指标）。"""

    def __init__(
        self,
        name: str,
        timeout: int = 30,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        self.name = name
        self.timeout = timeout
        self.params = params or {}
        self.optional = optional

    @staticmethod
    def _now() -> str:
        """返回当前 UTC 时间的 ISO 格式字符串。"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def close(self) -> None:
        """关闭底层连接（默认空操作，子类可按需覆盖）。

        调用 super().close() 沿 MRO 链将关闭动作传递给后续基类
        （如 _HttpClientMixin 会关闭 httpx 客户端），保证 MRO 上所有
        基类的资源释放逻辑都被执行。
        """
        await super().close()

    async def search(self, keyword: str) -> list[dict]:
        """默认空实现：子类按需覆盖。"""
        return []

    async def quote(self, symbols: list[str]) -> list[dict]:
        """默认空实现：子类按需覆盖。"""
        return []

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        """默认空实现：子类按需覆盖。"""
        return []

    async def finance(self, symbol: str) -> dict:
        """默认空实现：子类按需覆盖。"""
        return {}

    async def fund_flow(self, symbol: str) -> dict:
        """默认空实现：子类按需覆盖。"""
        return {}

    async def technical(self, symbol: str) -> dict:
        """默认空实现：子类按需覆盖。"""
        return {}


class NewsProvider(ABC):
    """新闻数据采集提供者。"""

    def __init__(
        self,
        name: str,
        timeout: int = 30,
        params: dict | None = None,
        optional: bool = False,
    ) -> None:
        self.name = name
        self.timeout = timeout
        self.params = params or {}
        self.optional = optional

    @staticmethod
    def _now() -> str:
        """返回当前 UTC 时间的 ISO 格式字符串。"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def close(self) -> None:
        """关闭底层连接（默认空操作，子类可按需覆盖）。

        调用 super().close() 沿 MRO 链将关闭动作传递给后续基类
        （如 _HttpClientMixin 会关闭 httpx 客户端），保证 MRO 上所有
        基类的资源释放逻辑都被执行。
        """
        await super().close()

    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]:
        """默认空实现：子类按需覆盖。"""
        return []


# 向后兼容：旧代码可继续继承 BaseProvider。
# 实际为 StructuredProvider + NewsProvider 的多继承占位。
class BaseProvider(StructuredProvider, NewsProvider):
    """旧基类，新代码应直接继承 StructuredProvider 或 NewsProvider。"""
