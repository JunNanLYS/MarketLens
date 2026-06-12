"""情感分析结果数据模型。

定义 SentimentResult 数据类，供 sentiment 子模块和 news_service 共用。
低置信度时自动降级为 neutral，避免模型不确定时给出错误方向。
"""

from dataclasses import dataclass


@dataclass
class SentimentResult:
    """单条新闻的情感分析结果。

    Attributes:
        sentiment: 情感类别 — positive / negative / neutral
        confidence: 置信度 0.0-1.0，低于 threshold 时降级为 neutral
        reason: 一句话中文理由，供审计追溯
    """

    sentiment: str  # Literal["positive", "negative", "neutral"]
    confidence: float
    reason: str

    def to_db_value(self, threshold: float = 0.4) -> str:
        """低置信度时降级为 neutral，保证数据库中不会出现低质量的正/负面判断。

        Args:
            threshold: 置信度阈值，低于此值时降级为 neutral。

        Returns:
            写入 news_items.sentiment 列的值。
        """
        if self.confidence < threshold:
            return "neutral"
        return self.sentiment