"""情感分析子包。

公开接口：
- create_sentiment_analyzer(config) -> SentimentAnalyzer | None
  根据 config.yaml 中 sentiment 段创建分析器实例；
  optional=True 且无 key 时返回 None（调用方全部 fallback neutral）。

- SentimentResult（数据类，models.py 中定义）
"""

from backend.config import get_config
from backend.services.sentiment.base import SentimentAnalyzer
from backend.services.sentiment.deepseek_provider import DeepSeekSentimentAnalyzer


def create_sentiment_analyzer(config: dict | None = None) -> SentimentAnalyzer | None:
    """根据配置创建情感分析器实例。

    Args:
        config: 配置字典，默认从 config.yaml 加载。

    Returns:
        SentimentAnalyzer 实例，或 None（optional=True 且无 API key 时）。
    """
    if config is None:
        config = get_config()

    sentiment_cfg: dict = config.get("sentiment", {})
    if not sentiment_cfg:
        # 配置段缺失 → 不启用情感分析
        return None

    provider: str = sentiment_cfg.get("provider", "deepseek")
    optional: bool = sentiment_cfg.get("optional", True)

    if provider == "deepseek":
        return DeepSeekSentimentAnalyzer(
            api_key=sentiment_cfg.get("api_key", ""),
            base_url=sentiment_cfg.get("base_url", "https://api.deepseek.com/v1"),
            model=sentiment_cfg.get("model", "deepseek-chat"),
            timeout=sentiment_cfg.get("timeout", 30),
            optional=optional,
        )

    # 未知 provider → 警告并返回 None
    from loguru import logger

    logger.warning("未知 sentiment provider: {}，跳过情感分析", provider)
    return None


__all__ = ["create_sentiment_analyzer", "SentimentAnalyzer"]