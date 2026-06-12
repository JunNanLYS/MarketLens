"""DeepSeek-v4-pro 情感分析 Provider。

逐条调用 DeepSeek API，传入系统提示词 + 新闻内容，解析返回的 JSON 得到情感分类。
遵循 project 异步硬约束：httpx.AsyncClient 懒加载 + close 幂等 + optional 降级。
"""

import json
import os
from typing import Any

import httpx
from loguru import logger

from backend.services.sentiment.base import SentimentAnalyzer
from backend.services.sentiment.models import SentimentResult

# ---------------------------------------------------------------------------
# 系统提示词：金融新闻情感分类
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
你是金融新闻情感分析师。对下述新闻判断其对相关标的的影响方向。

## 分类标准
- positive: 明确利好，有合理逻辑推断将推动标的上涨
- negative: 明确利空，有合理逻辑推断将导致标的价格下跌
- neutral: 信息不足、影响方向矛盾、或为纯信息通报（人事变动/数据发布等无方向性事件）

## 重要规则
1. 宁可判断也不要逃避 — 仅在确实无法判断方向时才标 neutral
2. 从投资者视角判断：这条消息会让持有者担忧还是兴奋？
3. 一条新闻可能对不同标的有不同影响 — 需要综合判断市场整体倾向

## 受影响板块（sectors）
识别该新闻直接或间接影响的A股行业板块/概念板块/资产类别。
例如：某地爆发冲突 → 石油、贵金属、军工、航运受影响。
- 尽量使用公认的板块名称（如：石油、银行、新能源、军工、贵金属、航运等）
- 没有明确影响板块时输出空列表 []
- 一条新闻可影响多个板块，不要遗漏

## 输出格式（严格 JSON，不要输出其他内容）
{"sentiment": "positive 或 negative 或 neutral", "confidence": 0.0到1.0的浮点数, "reason": "一句话中文理由", "sectors": ["板块1", "板块2"]}"""


class DeepSeekSentimentAnalyzer(SentimentAnalyzer):
    """基于 DeepSeek-v4-pro 的情感分析器。

    设计要点：
    1. 懒加载 httpx.AsyncClient（与 project Provider 模式一致）
    2. optional=True 时 API key 缺失 → 静默降级，全部返回 None
    3. 单条调用失败不阻塞其他条，对应位置返回 None
    4. 通过 confidence threshold 在 SentimentResult.to_db_value() 中降级
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: int = 30,
        optional: bool = True,
    ) -> None:
        # 环境变量优先级高于构造参数
        self._api_key: str = os.environ.get("DEEPSEEK_API_KEY", api_key)
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self.optional = optional
        self._client: httpx.AsyncClient | None = None

        # optional=True 且无 key → 标记为不可用，analyze 直接返回全 None
        self._available: bool = bool(self._api_key) or not optional

    async def _get_client(self) -> httpx.AsyncClient:
        """懒加载 httpx.AsyncClient，避免 import 时阻塞。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def close(self) -> None:
        """关闭 httpx 客户端，幂等。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def analyze(self, items: list[dict]) -> list[SentimentResult | None]:
        """逐条发送新闻到 DeepSeek，并发获取情感分析结果。

        Args:
            items: 新闻字典列表，每条至少包含 title 字段。

        Returns:
            与 items 等长的列表，每项为 SentimentResult 或 None（失败时）。
        """
        if not self._available:
            logger.warning("DeepSeek 情感分析不可用（optional=True + 无 API key），全部降级为 neutral")
            return [None] * len(items)

        if not items:
            return []

        # 并发调用，DeepSeek 支持 500 并发无需限流
        tasks = [self._analyze_single(item) for item in items]
        import asyncio

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: list[SentimentResult | None] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.exception(
                    "新闻情感分析失败 (title={}): {}",
                    items[i].get("title", "")[:50],
                    result,
                )
                output.append(None)
            else:
                output.append(result)
        return output

    async def _analyze_single(self, item: dict) -> SentimentResult | None:
        """对单条新闻调用 DeepSeek API。

        构造用户消息：截取 title + content（如有），发送到 DeepSeek，
        解析返回的 JSON 获得 SentimentResult。
        """
        # 构造用户消息：标题 + 正文（如有）
        title = item.get("title", "")
        content = item.get("content") or item.get("summary") or ""
        user_message = f"标题：{title}"
        if content:
            # 截取前 2000 字，避免 token 过长
            user_message += f"\n内容：{content[:2000]}"

        client = await self._get_client()

        try:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                "DeepSeek API 返回错误 status={}: {}",
                e.response.status_code,
                e.response.text[:200],
            )
            return None
        except httpx.RequestError as e:
            logger.error("DeepSeek API 请求失败: {}", e)
            return None

        # 解析返回 JSON
        return self._parse_response(response.json(), title)

    @staticmethod
    def _parse_response(data: dict[str, Any], title: str = "") -> SentimentResult | None:
        """从 DeepSeek 响应中提取 SentimentResult。

        兼容 response_format=json_object 和裸文本 JSON 两种返回格式。
        """
        try:
            # 标准 OpenAI 兼容格式
            content: str = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError):
            logger.warning("DeepSeek 响应解析失败 (title={})", title[:50])
            return None

        sentiment = parsed.get("sentiment", "neutral").lower()
        if sentiment not in ("positive", "negative", "neutral"):
            sentiment = "neutral"

        confidence = parsed.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        reason = parsed.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)

        sectors = parsed.get("sectors", [])
        if not isinstance(sectors, list):
            sectors = []
        # 过滤非字符串元素
        sectors = [s for s in sectors if isinstance(s, str)]

        return SentimentResult(
            sentiment=sentiment,
            confidence=confidence,
            reason=reason,
            sectors=sectors,
        )