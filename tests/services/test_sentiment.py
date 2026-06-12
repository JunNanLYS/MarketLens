"""sentiment 子模块单元测试。

覆盖：
- models.py: SentimentResult 数据类及 to_db_value() 降级逻辑
- base.py: SentimentAnalyzer ABC 接口
- deepseek_provider.py: DeepSeekSentimentAnalyzer 核心
  - API key 缺失时 optional 降级
  - 响应 JSON 解析
  - 单条失败不阻塞其他条
  - _parse_response 容错
- __init__.py: create_sentiment_analyzer() 工厂
- 与 NewsService 集成：sentiment_analyzer=False 跳过分析
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.sentiment.models import SentimentResult
from backend.services.sentiment.deepseek_provider import DeepSeekSentimentAnalyzer
from backend.services.sentiment import create_sentiment_analyzer


# ---------------------------------------------------------------------------
# models.py 测试
# ---------------------------------------------------------------------------


class TestSentimentResult:
    """SentimentResult 数据类及 to_db_value 降级逻辑。"""

    def test_positive_high_confidence(self) -> None:
        r = SentimentResult(sentiment="positive", confidence=0.9, reason="利好消息")
        assert r.to_db_value() == "positive"

    def test_negative_high_confidence(self) -> None:
        r = SentimentResult(sentiment="negative", confidence=0.8, reason="利空消息")
        assert r.to_db_value() == "negative"

    def test_neutral_high_confidence(self) -> None:
        r = SentimentResult(sentiment="neutral", confidence=0.7, reason="无方向性")
        assert r.to_db_value() == "neutral"

    def test_low_confidence_downgrades_to_neutral(self) -> None:
        """置信度低于 0.55 时，positive/negative 都降级为 neutral。"""
        r1 = SentimentResult(sentiment="positive", confidence=0.3, reason="不太确定")
        assert r1.to_db_value() == "neutral"

        r2 = SentimentResult(sentiment="negative", confidence=0.1, reason="几乎瞎猜")
        assert r2.to_db_value() == "neutral"

    def test_custom_threshold(self) -> None:
        r = SentimentResult(sentiment="positive", confidence=0.5, reason="还行")
        assert r.to_db_value(threshold=0.4) == "positive"
        assert r.to_db_value(threshold=0.6) == "neutral"

    def test_confidence_at_threshold_boundary(self) -> None:
        """confidence == threshold 时不降级（>= 判断）。"""
        r = SentimentResult(sentiment="positive", confidence=0.4, reason="边界")
        assert r.to_db_value(threshold=0.4) == "positive"

    def test_zero_confidence(self) -> None:
        r = SentimentResult(sentiment="negative", confidence=0.0, reason="完全不确定")
        assert r.to_db_value() == "neutral"

    def test_sectors_default_empty(self) -> None:
        """不传 sectors 时默认为空列表。"""
        r = SentimentResult(sentiment="neutral", confidence=0.5, reason="测试")
        assert r.sectors == []

    def test_sectors_preserved(self) -> None:
        """sectors 正确传入和保存。"""
        r = SentimentResult(
            sentiment="negative", confidence=0.8, reason="地缘冲突",
            sectors=["石油", "贵金属", "军工"],
        )
        assert r.sectors == ["石油", "贵金属", "军工"]


# ---------------------------------------------------------------------------
# deepseek_provider.py 测试
# ---------------------------------------------------------------------------


class TestDeepSeekSentimentAnalyzer:
    """DeepSeek 情感分析器核心逻辑。"""

    def test_init_with_api_key_available(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            analyzer = DeepSeekSentimentAnalyzer(
                api_key="sk-test-key", optional=True
            )
            assert analyzer._available is True
            assert analyzer._api_key == "sk-test-key"

    def test_init_without_key_optional_true(self) -> None:
        """optional=True 且无 key → 不可用，analyze 返回全 None。"""
        with patch.dict("os.environ", {}, clear=True):
            analyzer = DeepSeekSentimentAnalyzer(
                api_key="", optional=True
            )
            assert analyzer._available is False

    def test_init_without_key_optional_false(self) -> None:
        """optional=False 且无 key → 仍可用（会在调用时报错）。"""
        analyzer = DeepSeekSentimentAnalyzer(
            api_key="", optional=False
        )
        assert analyzer._available is True

    def test_env_var_overrides_config_key(self) -> None:
        """DEEPSEEK_API_KEY 环境变量优先于配置文件中的 key。"""
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-env-key"}, clear=False):
            analyzer = DeepSeekSentimentAnalyzer(
                api_key="sk-config-key", optional=True
            )
            assert analyzer._api_key == "sk-env-key"
            assert analyzer._available is True

    async def test_analyze_returns_none_when_unavailable(self) -> None:
        """不可用时 analyze 返回全 None 列表。"""
        # 显式屏蔽 env：env 里有 DEEPSEEK_API_KEY 时 _api_key 会被覆盖，
        # 导致 _available 仍为 True，测试无法走降级路径。
        with patch.dict("os.environ", {}, clear=True):
            analyzer = DeepSeekSentimentAnalyzer(api_key="", optional=True)
            items = [{"title": "测试"}]
            results = await analyzer.analyze(items)
            assert results == [None]

    async def test_analyze_empty_list(self) -> None:
        analyzer = DeepSeekSentimentAnalyzer(api_key="sk-test", optional=True)
        results = await analyzer.analyze([])
        assert results == []

    async def test_analyze_success_mock(self) -> None:
        """模拟成功 API 调用，验证返回 SentimentResult。"""
        analyzer = DeepSeekSentimentAnalyzer(
            api_key="sk-test", optional=True
        )
        # 注入 mock client，跳过懒加载
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "sentiment": "positive",
                            "confidence": 0.85,
                            "reason": "央行降息利好市场",
                        })
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        analyzer._client = mock_client

        items = [{"title": "央行降息刺激市场"}, {"title": "某公司发布财报"}]
        results = await analyzer.analyze(items)

        assert len(results) == 2
        assert results[0] is not None
        assert results[0].sentiment == "positive"
        assert results[0].confidence == 0.85
        assert "降息" in results[0].reason

        # 验证请求体开启了思考模式（v4-pro + thinking enabled）
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["model"] == "deepseek-v4-pro"  # 默认 model
        assert body["thinking"] == {"type": "enabled"}
        assert body["reasoning_effort"] == "high"
        assert body["max_tokens"] == 1500

    async def test_thinking_disabled_omits_thinking_field(self) -> None:
        """思考关闭时请求体不应含 thinking/reasoning_effort 字段（兼容 cheap 模式）。"""
        analyzer = DeepSeekSentimentAnalyzer(
            api_key="sk-test",
            thinking_enabled=False,
        )
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"sentiment":"neutral","confidence":0.5,"reason":"x"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        analyzer._client = mock_client

        await analyzer.analyze([{"title": "test"}])

        body = mock_client.post.call_args.kwargs["json"]
        assert "thinking" not in body
        assert "reasoning_effort" not in body

    async def test_analyze_single_failure_does_not_block_others(self) -> None:
        """单条失败对应位置返回 None，不阻塞其他条。"""
        analyzer = DeepSeekSentimentAnalyzer(
            api_key="sk-test", optional=True
        )
        mock_client = AsyncMock()

        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一条请求失败
                raise Exception("API timeout")
            resp = MagicMock()
            resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"sentiment": "negative", "confidence": 0.7, "reason": "利空消息"}'
                    }
                }]
            }
            resp.raise_for_status = MagicMock()
            return resp

        mock_client.post = mock_post
        analyzer._client = mock_client

        items = [{"title": "失败测试"}, {"title": "成功测试"}]
        results = await analyzer.analyze(items)

        assert len(results) == 2
        assert results[0] is None  # 失败 → None
        assert results[1] is not None
        assert results[1].sentiment == "negative"

    async def test_close_idempotent(self) -> None:
        """close() 幂等且 client 置 None。"""
        analyzer = DeepSeekSentimentAnalyzer(api_key="sk-test", optional=True)
        mock_client = AsyncMock()
        analyzer._client = mock_client
        await analyzer.close()
        assert analyzer._client is None
        # 第二次 close 不报错
        await analyzer.close()

    def test_parse_response_valid_json(self) -> None:
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "positive",
                        "confidence": 0.9,
                        "reason": "利好",
                        "sectors": ["新能源", "电动车"],
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data, "测试")
        assert result is not None
        assert result.sentiment == "positive"
        assert result.confidence == 0.9
        assert result.sectors == ["新能源", "电动车"]

    def test_parse_response_invalid_sentiment_defaults_neutral(self) -> None:
        """模型返回非法 sentiment 值时降级为 neutral。"""
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "bullish",  # 非法值
                        "confidence": 0.8,
                        "reason": "看好",
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data, "测试")
        assert result is not None
        assert result.sentiment == "neutral"

    def test_parse_response_missing_confidence_defaults_half(self) -> None:
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "positive",
                        "reason": "利好",
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data, "测试")
        assert result is not None
        assert result.confidence == 0.5

    def test_parse_response_exception_returns_none(self) -> None:
        """API 返回非 JSON 或结构异常时返回 None。"""
        # 非 JSON content
        data = {"choices": [{"message": {"content": "not valid json!!!"}}]}
        result = DeepSeekSentimentAnalyzer._parse_response(data, "测试")
        assert result is None

        # 缺少 choices
        data2 = {"error": "bad request"}
        result2 = DeepSeekSentimentAnalyzer._parse_response(data2, "测试")
        assert result2 is None

    def test_parse_response_confidence_out_of_range_clamped(self) -> None:
        """confidence 超出 [0, 1] 范围时裁剪。"""
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "positive",
                        "confidence": 1.5,
                        "reason": "超强利好",
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data)
        assert result is not None
        assert result.confidence == 1.0

        data["choices"][0]["message"]["content"] = json.dumps({
            "sentiment": "negative",
            "confidence": -0.3,
            "reason": "超强利空",
        })
        result = DeepSeekSentimentAnalyzer._parse_response(data)
        assert result is not None
        assert result.confidence == 0.0

    def test_parse_response_sectors_missing_defaults_empty(self) -> None:
        """模型未返回 sectors 时默认为空列表。"""
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "neutral",
                        "confidence": 0.5,
                        "reason": "无影响",
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data)
        assert result is not None
        assert result.sectors == []

    def test_parse_response_sectors_non_list_defaults_empty(self) -> None:
        """sectors 返回非列表时降级为空列表。"""
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "positive",
                        "confidence": 0.7,
                        "reason": "利好",
                        "sectors": "石油",
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data)
        assert result is not None
        assert result.sectors == []

    def test_parse_response_sectors_filters_non_strings(self) -> None:
        """sectors 列表中非字符串元素被过滤。"""
        data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "sentiment": "negative",
                        "confidence": 0.8,
                        "reason": "冲突",
                        "sectors": ["石油", 123, None, "军工"],
                    })
                }
            }]
        }
        result = DeepSeekSentimentAnalyzer._parse_response(data)
        assert result is not None
        assert result.sectors == ["石油", "军工"]


# ---------------------------------------------------------------------------
# __init__.py 测试
# ---------------------------------------------------------------------------


class TestCreateSentimentAnalyzer:
    """工厂函数测试。"""

    def test_no_config_returns_none(self) -> None:
        """配置段缺失时返回 None（不启用情感分析）。"""
        result = create_sentiment_analyzer(config={})
        assert result is None

    def test_deepseek_provider_created(self) -> None:
        """配置正确时创建 DeepSeekSentimentAnalyzer 实例。"""
        with patch.dict("os.environ", {}, clear=True):
            config = {
                "sentiment": {
                    "provider": "deepseek",
                    "api_key": "sk-test",
                    "optional": True,
                }
            }
            analyzer = create_sentiment_analyzer(config=config)
            assert isinstance(analyzer, DeepSeekSentimentAnalyzer)
            assert analyzer._api_key == "sk-test"

    def test_unknown_provider_returns_none(self) -> None:
        """未知 provider 警告并返回 None。"""
        config = {
            "sentiment": {
                "provider": "unknown_provider",
                "api_key": "sk-test",
            }
        }
        result = create_sentiment_analyzer(config=config)
        assert result is None

    def test_deepseek_env_var_overrides_config(self) -> None:
        """DEEPSEEK_API_KEY 环境变量优先。"""
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-from-env"}, clear=False):
            config = {
                "sentiment": {
                    "provider": "deepseek",
                    "api_key": "sk-from-config",
                    "optional": True,
                }
            }
            analyzer = create_sentiment_analyzer(config=config)
            assert isinstance(analyzer, DeepSeekSentimentAnalyzer)
            assert analyzer._api_key == "sk-from-env"