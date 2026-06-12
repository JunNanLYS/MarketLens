"""情感分析器抽象基类。

所有情感分析 Provider 必须继承 SentimentAnalyzer 并实现 analyze 方法。
设计遵循 project 的 Provider 模式：optional=True 时 key 缺失或服务不可用则静默降级。
"""

from abc import ABC, abstractmethod

from backend.services.sentiment.models import SentimentResult


class SentimentAnalyzer(ABC):
    """情感分析器 ABC。

    子类只需实现 analyze() 方法：接收新闻列表，返回对应的情感分析结果列表。
    单条失败时对应位置返回 None，由调用方决定 fallback 策略。
    """

    @abstractmethod
    async def analyze(self, items: list[dict]) -> list[SentimentResult | None]:
        """对新闻列表批量进行情感分析。

        Args:
            items: 新闻字典列表，每条至少包含 title 字段，
                   可选 content / summary 用于辅助判断。

        Returns:
            与 items 等长的列表；每项为 SentimentResult 或 None（该条分析失败）。
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭底层连接（httpx 客户端等）。"""
        ...