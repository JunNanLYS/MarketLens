import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from backend.collectors.sina import SinaProvider


@pytest.fixture
async def provider() -> SinaProvider:
    return SinaProvider(
        name="sina",
        timeout=15,
        params={"quote_url": "https://hq.sinajs.cn/list={codes}"},
    )


def _make_provider() -> SinaProvider:
    """创建干净的 SinaProvider 用于测试。"""
    return SinaProvider(
        name="sina",
        timeout=15,
        params={"quote_url": "https://hq.sinajs.cn/list={codes}"},
    )


def _inject_client(provider: SinaProvider, mock_get: AsyncMock) -> None:
    """将 mock 注入 provider._client.get，绕过懒加载。"""
    provider._client = MagicMock()
    provider._client.get = mock_get


async def test_init(provider: SinaProvider) -> None:
    assert provider.name == "sina"
    assert provider.timeout == 15
    assert provider.quote_url == "https://hq.sinajs.cn/list={codes}"
    assert provider.optional is False


async def test_to_sina_code_sh() -> None:
    assert SinaProvider._to_sina_code("600519") == "sh600519"


async def test_to_sina_code_sz() -> None:
    assert SinaProvider._to_sina_code("000001") == "sz000001"


async def test_to_sina_code_sz3() -> None:
    assert SinaProvider._to_sina_code("300001") == "sz300001"


async def test_to_sina_code_already_prefixed() -> None:
    assert SinaProvider._to_sina_code("sh600519") == "sh600519"
    assert SinaProvider._to_sina_code("sz000001") == "sz000001"


async def test_to_sina_code_hk_us() -> None:
    assert SinaProvider._to_sina_code("hk00700") == "hk00700"
    assert SinaProvider._to_sina_code("usAAPL") == "usAAPL"


async def test_strip_code_for_finance() -> None:
    assert SinaProvider._strip_code_for_finance("sh600519") == "600519"
    assert SinaProvider._strip_code_for_finance("sz000001") == "000001"
    assert SinaProvider._strip_code_for_finance("hk00700") is None
    assert SinaProvider._strip_code_for_finance("600519") == "600519"
    assert SinaProvider._strip_code_for_finance("abc") is None


async def test_market_prefix() -> None:
    assert SinaProvider._market_prefix("sh600519") == "sh"
    assert SinaProvider._market_prefix("sz000001") == "sz"
    assert SinaProvider._market_prefix("600519") == "sh"
    assert SinaProvider._market_prefix("000001") == "sz"
    assert SinaProvider._market_prefix("300001") == "sz"


async def test_safe_float() -> None:
    assert SinaProvider._safe_float(None) is None
    assert SinaProvider._safe_float("") is None
    assert SinaProvider._safe_float("abc") is None
    assert SinaProvider._safe_float(123) == 123.0
    assert SinaProvider._safe_float("123.45") == 123.45
    assert SinaProvider._safe_float("1,234.56") == 1234.56
    assert SinaProvider._safe_float("-28.80") == -28.80


# ── quote 测试 ───────────────────────────────────────────────


async def test_quote_success(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1800.00,1790.00,1810.00,1820.00,1795.00,'
        "1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,"
        "3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,"
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";'
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519"])
    assert len(result) == 1
    assert result[0]["symbol"] == "sh600519"
    assert result[0]["price"] == 1810.0
    assert result[0]["open"] == 1800.0
    assert result[0]["prev_close"] == 1790.0
    assert result[0]["source"] == "sina"
    assert "collected_at" in result[0]


async def test_quote_change_calculation(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1790.00,1790.00,1800.00,1810.00,1785.00,'
        "1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,"
        "3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,"
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";'
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519"])
    assert len(result) == 1
    assert result[0]["change"] == 10.0
    assert result[0]["change_pct"] == round(10.0 / 1790.0 * 100, 2)
    assert result[0]["amplitude"] == round(25.0 / 1790.0 * 100, 2)


async def test_quote_multiple_symbols(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1800.00,1790.00,1810.00,1820.00,1795.00,'
        "1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,"
        "3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,"
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";\n'
        'var hq_str_sz000001="平安银行,12.00,11.90,12.10,12.20,11.95,'
        "12.05,12.06,100000,1200000.00,500,12.05,600,12.06,"
        "700,12.07,800,12.08,900,12.09,1000,12.10,"
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";'
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519", "sz000001"])
    assert len(result) == 2


async def test_quote_timeout_returns_empty(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519"])
    assert result == []


async def test_quote_http_error_returns_empty(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )
    )
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519"])
    assert result == []


async def test_quote_generic_exception_returns_empty(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=ConnectionError("network error"))
    _inject_client(provider, mock_get)

    result = await provider.quote(["sh600519"])
    assert result == []


async def test_quote_empty_symbols(provider: SinaProvider) -> None:
    result = await provider.quote([])
    assert result == []


async def test_search_empty_keyword(provider: SinaProvider) -> None:
    """空 keyword 直接返回 []，不发起 HTTP 请求。"""
    result = await provider.search("")
    assert result == []


async def test_search_parses_suggest_response(provider: SinaProvider) -> None:
    """单条与多条 Sina suggest 响应均能解析出 fullcode + 名称。"""
    # 真实 Sina 响应（GBK 编码，含多条 ; 分隔）
    gbk_text = (
        'var suggestvalue="宁德时代,11,300750,sz300750,宁德时代,,宁德时代,99,1,ESG,,;'
        '贵州茅台,11,600519,sh600519,贵州茅台,,贵州茅台,99,1,ESG,,";'
        '"'
    ).encode("gbk")
    mock_resp = MagicMock()
    mock_resp.content = gbk_text
    mock_resp.text = gbk_text.decode("gbk")
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.search("宁德")
    assert len(result) == 2
    assert result[0]["symbol"] == "sz300750"
    assert result[0]["name"] == "宁德时代"
    assert result[0]["market"] == "sz"
    assert result[0]["asset_type"] == "stock"
    assert result[1]["symbol"] == "sh600519"
    assert result[1]["market"] == "sh"


async def test_search_empty_payload(provider: SinaProvider) -> None:
    """Sina 返回空字符串（搜不到）→ []。"""
    mock_resp = MagicMock()
    mock_resp.content = b'var suggestvalue="";'
    mock_resp.text = 'var suggestvalue="";'
    mock_resp.raise_for_status = MagicMock()
    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.search("不存在的标的")
    assert result == []


async def test_search_skips_short_items(provider: SinaProvider) -> None:
    """字段不足的条目被跳过。"""
    text = 'var suggestvalue="bad,11,300750;good,11,300750,sz300750,宁德时代,...";'
    mock_resp = MagicMock()
    mock_resp.content = text.encode("utf-8")
    mock_resp.text = text
    mock_resp.raise_for_status = MagicMock()
    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.search("宁德")
    assert len(result) == 1
    assert result[0]["symbol"] == "sz300750"


async def test_search_timeout_returns_empty(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    _inject_client(provider, mock_get)

    result = await provider.search("茅台")
    assert result == []


async def test_search_http_error_returns_empty(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 456
    mock_get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_resp
        )
    )
    _inject_client(provider, mock_get)

    result = await provider.search("茅台")
    assert result == []


async def test_technical_returns_empty(provider: SinaProvider) -> None:
    assert await provider.technical("sh600519") == {}


# ── kline 测试 ────────────────────────────────────────────────


async def test_kline_success(provider: SinaProvider) -> None:
    mock_data = [
        {
            "day": "2026-06-01",
            "open": "1327.000",
            "high": "1327.000",
            "low": "1301.310",
            "close": "1309.600",
            "volume": "43845",
        },
        {
            "day": "2026-05-29",
            "open": "1270.600",
            "high": "1329.000",
            "low": "1270.000",
            "close": "1326.000",
            "volume": "76478",
        },
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519")

    assert len(result) == 2
    assert result[0]["symbol"] == "sh600519"
    assert result[0]["open"] == 1327.0
    assert result[0]["close"] == 1309.6
    assert result[0]["volume"] == 43845.0
    assert result[0]["source"] == "sina"
    assert "collected_at" in result[0]
    assert result[0]["change_pct"] is None


async def test_kline_hk_returns_empty(provider: SinaProvider) -> None:
    result = await provider.kline("hk00700")
    assert result == []


async def test_kline_us_returns_empty(provider: SinaProvider) -> None:
    result = await provider.kline("usAAPL")
    assert result == []


async def test_kline_empty_response(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519")
    assert result == []


async def test_kline_non_list_response(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": "not found"}
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519")
    assert result == []


async def test_kline_timeout(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519")
    assert result == []


async def test_kline_http_error(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )
    )
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519")
    assert result == []


async def test_kline_weekly_period(provider: SinaProvider) -> None:
    mock_data = [
        {
            "day": "2026-06-01",
            "open": "1300",
            "high": "1320",
            "low": "1290",
            "close": "1310",
            "volume": "100000",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.kline("sh600519", period="weekly")
    assert len(result) == 1
    # 验证内部映射常量
    assert SinaProvider._PERIOD_SCALE["weekly"] == 1200


async def test_kline_monthly_period(provider: SinaProvider) -> None:
    mock_data = [
        {
            "day": "2026-05-01",
            "open": "1300",
            "high": "1310",
            "low": "1290",
            "close": "1305",
            "volume": "200000",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    await provider.kline("sh600519", period="monthly")
    # 验证内部映射常量
    assert SinaProvider._PERIOD_SCALE["monthly"] == 7200


# ── finance 测试 ──────────────────────────────────────────────


async def test_finance_success(provider: SinaProvider) -> None:
    html = (
        "<html><body>"
        "<td>报告期：2025-12-31</td>"
        "<td>营业收入 1,688,381.03</td>"
        "<td>净利润 823,200.67</td>"
        "<td>每股收益 65.66</td>"
        "<td>净资产收益率 22.50</td>"
        "</body></html>"
    )
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.finance("sh600519")

    assert result["symbol"] == "sh600519"
    assert result["report_period"] == "2025-12-31"
    assert result["revenue"] == pytest.approx(16883810300.0, rel=0.1)
    assert result["net_profit"] == pytest.approx(8232006700.0, rel=0.1)
    assert result["eps"] == 65.66
    assert result["roe"] == 22.50
    assert result["source"] == "sina"
    assert result["revenue_yoy"] is None
    assert "collected_at" in result


async def test_finance_non_a_share(provider: SinaProvider) -> None:
    result = await provider.finance("hk00700")
    # 非 A 股按新约定返回 None（修复 ISSUES.md 2026-06-05 边界条件条目）
    assert result is None


async def test_finance_timeout(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    _inject_client(provider, mock_get)

    result = await provider.finance("sh600519")
    assert result is None


async def test_finance_http_error(provider: SinaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        )
    )
    _inject_client(provider, mock_get)

    result = await provider.finance("sh600519")
    assert result is None


# ── fund_flow 测试 ───────────────────────────────────────────


async def test_fund_flow_success(provider: SinaProvider) -> None:
    mock_json = [
        {
            "date": "2026-06-01",
            "main_net_inflow": -189981349.0,
            "superlarge_net": 100236788.0,
            "large_net": -290218137.0,
            "medium_net": 190296011.0,
            "small_net": -314662.0,
            "net_ratio": 0.01,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_json)
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.fund_flow("sh600519")

    assert result["symbol"] == "sh600519"
    assert result["date"] == "2026-06-01"
    assert result["main_net_inflow"] == -189981349.0
    assert result["super_large_net_inflow"] == 100236788.0
    assert result["large_net_inflow"] == -290218137.0
    assert result["medium_net_inflow"] == 190296011.0
    assert result["small_net_inflow"] == -314662.0
    assert result["net_inflow_ratio"] == 0.01
    assert result["source"] == "sina"
    assert "collected_at" in result


async def test_fund_flow_single_object(provider: SinaProvider) -> None:
    mock_data = {"date": "2026-06-01", "main_net_inflow": 50000000.0}
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_data)
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.fund_flow("sh600519")

    assert result["main_net_inflow"] == 50000000.0
    assert result["source"] == "sina"


async def test_fund_flow_non_a_share(provider: SinaProvider) -> None:
    result = await provider.fund_flow("hk00700")
    assert result == {}


async def test_fund_flow_timeout(provider: SinaProvider) -> None:
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    _inject_client(provider, mock_get)

    result = await provider.fund_flow("sh600519")
    assert result == {}


async def test_fund_flow_invalid_json(provider: SinaProvider) -> None:
    """JSON 解析失败时 _parse_fund_flow 返回 {}，fund_flow 直接返回空 dict。"""
    mock_resp = MagicMock()
    mock_resp.text = "not valid json at all"
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.fund_flow("sh600519")
    # 生产代码：JSON 解析失败时 _parse_fund_flow 返回 {}，fund_flow 透传 {}
    assert result == {}


async def test_fund_flow_empty_text(provider: SinaProvider) -> None:
    """空文本同样返回含 None 的默认结构（生产代码 line 264-265 显式返回 {}）。"""
    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_resp)
    _inject_client(provider, mock_get)

    result = await provider.fund_flow("sh600519")
    # 生产代码在 text 为空时直接 return {}（line 264-265），不进入 _parse_fund_flow
    # 但经过 if not text 判断后 result == {}，断言它为空
    assert result == {}
