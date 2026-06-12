"""情感分析子包。

公开接口：
- create_sentiment_analyzer(config, use_case="news") -> SentimentAnalyzer | None
  根据 config.yaml 中 sentiment 段创建分析器实例；
  optional=True 且无 key 时返回 None（调用方全部 fallback neutral）。
  use_case 控制 thinking 开关：news (默认关, 节省 token) / narrative_summary (开, 多步推理)。

- SentimentResult（数据类，models.py 中定义）
"""

from backend.config import get_config
from backend.services.sentiment.base import SentimentAnalyzer
from backend.services.sentiment.deepseek_provider import DeepSeekSentimentAnalyzer

# use_case 默认值：news 表示新闻情感分析，是最常见的调用点。
# 调用方显式传 narrative_summary 才会开启思考模式。
_DEFAULT_USE_CASE = "news"


def _resolve_thinking_for_use_case(
    sentiment_cfg: dict, use_case: str
) -> tuple[bool, str]:
    """根据 use_case 解析 thinking 配置。

    新配置结构（thinking_by_use_case）:
        sentiment:
          thinking_by_use_case:
            news: {enabled: false}
            narrative_summary: {enabled: true, reasoning_effort: high}

    老配置结构（thinking）做向后兼容降级 — 如果用户还在用 thinking.enabled,
    则不论 use_case 都按它来（默认 thinking_enabled=True）。

    Returns:
        (thinking_enabled, reasoning_effort) 元组。
    """
    # 优先读新的按 use_case 分组的配置
    by_use_case: dict = sentiment_cfg.get("thinking_by_use_case") or {}
    if use_case in by_use_case:
        uc_cfg: dict = by_use_case[use_case] or {}
        return bool(uc_cfg.get("enabled", False)), str(uc_cfg.get("reasoning_effort", "high"))

    # 老配置 thinking 段：不论 use_case 都用同一份（向后兼容）
    legacy: dict = sentiment_cfg.get("thinking") or {}
    if legacy:
        return bool(legacy.get("enabled", False)), str(legacy.get("reasoning_effort", "high"))

    # 配置缺失：news 默认关（省 token），其他默认开（多步推理）
    if use_case == _DEFAULT_USE_CASE:
        return False, "high"
    return True, "high"


def create_sentiment_analyzer(
    config: dict | None = None,
    use_case: str = _DEFAULT_USE_CASE,
) -> SentimentAnalyzer | None:
    """根据配置创建情感分析器实例。

    Args:
        config: 配置字典，默认从 config.yaml 加载。
        use_case: 调用场景标识，控制 thinking 开关。
            - "news" (默认): 新闻情感分析 — 任务简单, 关思考省 token
            - "narrative_summary": 综合判断 / narrative 生成 — 开思考做多步推理

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

    thinking_enabled, reasoning_effort = _resolve_thinking_for_use_case(
        sentiment_cfg, use_case
    )

    if provider == "deepseek":
        return DeepSeekSentimentAnalyzer(
            api_key=sentiment_cfg.get("api_key", ""),
            base_url=sentiment_cfg.get("base_url", "https://api.deepseek.com"),
            model=sentiment_cfg.get("model", "deepseek-v4-pro"),
            timeout=sentiment_cfg.get("timeout", 60),
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            optional=optional,
        )

    # 未知 provider → 警告并返回 None
    from loguru import logger

    logger.warning("未知 sentiment provider: {}，跳过情感分析", provider)
    return None


__all__ = ["create_sentiment_analyzer", "SentimentAnalyzer"]