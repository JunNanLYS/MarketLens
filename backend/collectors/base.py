from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """数据采集提供者抽象基类，所有 Provider 必须实现统一接口。"""

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

    @abstractmethod
    def search(self, keyword: str) -> list[dict]: ...

    @abstractmethod
    def quote(self, symbols: list[str]) -> list[dict]: ...

    @abstractmethod
    def kline(self, symbol: str, period: str = "daily") -> list[dict]: ...

    @abstractmethod
    def finance(self, symbol: str) -> dict: ...

    @abstractmethod
    def fund_flow(self, symbol: str) -> dict: ...

    @abstractmethod
    def technical(self, symbol: str) -> dict: ...
