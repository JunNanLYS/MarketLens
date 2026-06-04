from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """数据采集提供者抽象基类（异步版）。"""

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
        """关闭底层连接（默认空操作，子类可按需覆盖）。"""

    @abstractmethod
    async def search(self, keyword: str) -> list[dict]: ...

    @abstractmethod
    async def quote(self, symbols: list[str]) -> list[dict]: ...

    @abstractmethod
    async def kline(self, symbol: str, period: str = "daily") -> list[dict]: ...

    @abstractmethod
    async def finance(self, symbol: str) -> dict: ...

    @abstractmethod
    async def fund_flow(self, symbol: str) -> dict: ...

    @abstractmethod
    async def technical(self, symbol: str) -> dict: ...
