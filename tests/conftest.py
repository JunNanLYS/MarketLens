"""pytest 全局夹具与安全网。

设计目标
--------
1. **防止真实外部 API 调用消耗真金白银**：即使未来某条新测试漏 mock，
   试图对 `api.deepseek.com`（或其他已知付费端点）发起真实 HTTP，
   都会在 provider 层被立刻拦截并抛 `RuntimeError`。
2. **避免开发机误配环境变量**导致本地 `pytest` 静默打钱：
   `DEEPSEEK_API_KEY` 如果在 CI / 本机意外设了真实值，conftest 启动时清空。
3. 仍允许 `monkeypatch.setenv` / `patch.dict("os.environ", ...)` 在测试体内
   临时设/改环境变量（这些 patch 会作用于 analyzer 内的 `os.environ.get`）。
4. 不破坏已有测试：直接给 `analyzer._client = mock_client` 的测试**完全**不受
   本 conftest 影响（因为我们改的是 provider 的 HTTP 客户端获取路径，
   而 mock 测试直接替换了字段）。
"""

from __future__ import annotations

import pytest

# 已知付费 / 外部端点，测试期间绝不允许真实请求。
# 维护说明：新增付费 Provider 时同步加到此处。
DEEP_SEEK_HOSTS: frozenset[str] = frozenset({
    "api.deepseek.com",
})


def _make_guarded_get_client(real_get_client):
    """包装 provider 的 _get_client，对 deepseek host 直接拒绝。"""

    async def _guarded(self):
        # 测试体内若已显式 _client = mock_client，跳过我们的检查
        # （httpx.AsyncClient 实例不是 Mock 类型即可放行）
        client = await real_get_client(self)
        # 嗅探 base_url
        base = getattr(client, "_base_url", None)
        host = getattr(base, "host", None) if base is not None else None
        if host in DEEP_SEEK_HOSTS:
            raise RuntimeError(
                f"测试期间禁止真实调用 {host}（会扣钱）。"
                "请在测试中 mock 掉 _get_client，或参考 "
                "tests/services/test_sentiment.py 用 analyzer._client = AsyncMock()。"
            )
        return client

    return _guarded


@pytest.fixture(autouse=True)
def _block_real_deepseek_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """为每个测试自动装上 DeepSeek 拦截。

    实现：替换 `DeepSeekSentimentAnalyzer._get_client` 为守门版本，
    对 base_url 命中 `api.deepseek.com` 的客户端直接抛 RuntimeError。

    兼容点：
    - 直接 `analyzer._client = AsyncMock()` 的测试：完全不走 _get_client，跳过
    - 工厂创建 `create_sentiment_analyzer()` 的测试：使用同一 provider 类，受保护
    - 测试体内 monkeypatch 重新替换 _get_client 的测试：fixture 最后清理会还原
    """
    # 1) 清空真实 DEEPSEEK_API_KEY（若开发机意外设置）。
    #    测试体内若需要此 env 可用 monkeypatch.setenv 重新注入。
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # 2) 包装 provider._get_client
    from backend.services.sentiment import deepseek_provider

    original_get_client = deepseek_provider.DeepSeekSentimentAnalyzer._get_client
    guarded_get_client = _make_guarded_get_client(original_get_client)
    monkeypatch.setattr(
        deepseek_provider.DeepSeekSentimentAnalyzer,
        "_get_client",
        guarded_get_client,
    )
