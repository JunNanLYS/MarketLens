from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.collectors.neodata import NeoDataProvider


@pytest.fixture
async def provider() -> NeoDataProvider:
    """创建 NeoDataProvider；首次访问 _client 时再注入 AsyncMock。"""
    p = NeoDataProvider(
        name="neodata",
        timeout=30,
        params={"endpoint": "https://example.com/api", "token": "test_token"},
        optional=True,
    )
    return p


def _inject_query(provider: NeoDataProvider, mock_obj: object) -> None:
    """将 mock 对象注入 provider._client.query，绕过懒加载。"""
    provider._client = MagicMock()
    provider._client.query = mock_obj


async def test_search_parses_entities(provider: NeoDataProvider) -> None:
    mock_result = {
        "data": {
            "apiData": {
                "entity": [
                    {"code": "00700.HK", "name": "腾讯控股"},
                    {"code": "TCEHY.US", "name": "Tencent"},
                    {"code": "600519.SH", "name": "贵州茅台"},
                    {"code": "000001.SZ", "name": "平安银行"},
                    {"code": "NOMATCH.XX", "name": "未知"},
                ]
            }
        }
    }
    mock_query = AsyncMock(return_value=mock_result)
    _inject_query(provider, mock_query)

    result = await provider.search("腾讯")

    assert len(result) == 5
    assert result[0]["symbol"] == "00700.HK"
    assert result[0]["name"] == "腾讯控股"
    assert result[0]["market"] == "hk"
    assert result[1]["market"] == "us"
    assert result[2]["market"] == "sh"
    assert result[3]["market"] == "sz"
    assert result[4]["market"] == ""
    for item in result:
        assert item["source"] == "neodata"
        assert "collected_at" in item


async def test_search_returns_empty_on_failure(provider: NeoDataProvider) -> None:
    mock_query = AsyncMock(return_value=None)
    _inject_query(provider, mock_query)

    result = await provider.search("腾讯")
    assert result == []

    mock_query = AsyncMock(side_effect=Exception("boom"))
    _inject_query(provider, mock_query)

    result = await provider.search("腾讯")
    assert result == []


async def test_quote_parses_basic_info(provider: NeoDataProvider) -> None:
    mock_info = {
        "最新价": "380.40",
        "涨跌额": "5.20",
        "涨跌幅": "1.39%",
        "今开": "376.00",
        "最高": "382.00",
        "最低": "375.00",
        "昨收": "375.20",
        "成交量": "1500万",
        "成交额": "57亿",
    }

    async def mock_query(query_text: str, data_type: str = "all") -> dict:
        return {
            "data": {
                "apiData": {
                    "apiRecall": [
                        {
                            "type": "basic_info",
                            "content": "\n".join(
                                f"{k}：{v}" for k, v in mock_info.items()
                            ),
                        }
                    ]
                }
            }
        }

    mock_query_obj = AsyncMock(side_effect=mock_query)
    _inject_query(provider, mock_query_obj)

    result = await provider.quote(["00700.HK"])

    assert len(result) == 1
    item = result[0]
    assert item["symbol"] == "00700.HK"
    assert item["price"] == 380.40
    assert item["change"] == 5.20
    assert item["change_pct"] == 1.39
    assert item["open"] == 376.0
    assert item["high"] == 382.0
    assert item["low"] == 375.0
    assert item["prev_close"] == 375.20
    assert item["volume"] == 1500.0
    assert item["amount"] == 57.0
    assert item["source"] == "neodata"


async def test_quote_skips_symbol_on_failure(provider: NeoDataProvider) -> None:
    mock_query = AsyncMock(return_value=None)
    _inject_query(provider, mock_query)

    result = await provider.quote(["00700.HK", "TCEHY.US"])
    assert result == []


async def test_kline_returns_empty(provider: NeoDataProvider) -> None:
    assert await provider.kline("00700.HK") == []
    assert await provider.kline("00700.HK", period="weekly") == []


async def test_finance_parses_basic_info(provider: NeoDataProvider) -> None:
    mock_info = {
        "报告期": "2025Q1",
        "营业收入": "1800亿",
        "营收同比增长": "12.5%",
        "净利润": "500亿",
        "净利润同比增长": "8.3%",
        "每股收益": "5.25",
        "净资产收益率": "15.2%",
        "资产负债率": "45.6%",
        "毛利率": "52.3%",
        "净利率": "27.8%",
    }

    async def mock_query(query_text: str, data_type: str = "all") -> dict:
        return {
            "data": {
                "apiData": {
                    "apiRecall": [
                        {
                            "type": "basic_info",
                            "content": "\n".join(
                                f"{k}：{v}" for k, v in mock_info.items()
                            ),
                        }
                    ]
                }
            }
        }

    mock_query_obj = AsyncMock(side_effect=mock_query)
    _inject_query(provider, mock_query_obj)

    result = await provider.finance("00700.HK")

    assert result["report_period"] == "2025Q1"
    assert result["revenue"] == 1800.0
    assert result["revenue_yoy"] == 12.5
    assert result["net_profit"] == 500.0
    assert result["net_profit_yoy"] == 8.3
    assert result["eps"] == 5.25
    assert result["roe"] == 15.2
    assert result["debt_ratio"] == 45.6
    assert result["gross_margin"] == 52.3
    assert result["net_margin"] == 27.8
    assert result["source"] == "neodata"
    assert "collected_at" in result


async def test_fund_flow_parses_basic_info(provider: NeoDataProvider) -> None:
    mock_info = {
        "主力净流入": "3.5亿",
        "净流入占比": "2.1%",
    }

    async def mock_query(query_text: str, data_type: str = "all") -> dict:
        return {
            "data": {
                "apiData": {
                    "apiRecall": [
                        {
                            "type": "basic_info",
                            "content": "\n".join(
                                f"{k}：{v}" for k, v in mock_info.items()
                            ),
                        }
                    ]
                }
            }
        }

    mock_query_obj = AsyncMock(side_effect=mock_query)
    _inject_query(provider, mock_query_obj)

    result = await provider.fund_flow("00700.HK")

    assert result["main_net_inflow"] == 3.5
    assert result["net_inflow_ratio"] == 2.1
    assert result["source"] == "neodata"
    assert "collected_at" in result


async def test_technical_returns_empty(provider: NeoDataProvider) -> None:
    assert await provider.technical("00700.HK") == {}


async def test_fetch_news_parses_doc_data(provider: NeoDataProvider) -> None:
    mock_result = {
        "data": {
            "docData": {
                "docRecall": [
                    {
                        "docList": [
                            {
                                "title": "腾讯发布Q1财报",
                                "source": "财联社",
                                "url": "https://example.com/1",
                                "content": "腾讯控股发布2025年第一季度财报...",
                                "publishTime": 1748736000,
                            },
                            {
                                "title": "腾讯回购股份",
                                "source": "新浪财经",
                                "url": "https://example.com/2",
                                "content": None,
                                "publishTime": None,
                            },
                        ]
                    }
                ]
            }
        }
    }

    mock_query = AsyncMock(return_value=mock_result)
    _inject_query(provider, mock_query)

    result = await provider.fetch_news(symbols=["00700.HK"])

    assert len(result) == 2
    assert result[0]["title"] == "腾讯发布Q1财报"
    assert result[0]["source"] == "财联社"
    assert result[0]["url"] == "https://example.com/1"
    assert result[0]["published_at"] is not None
    assert result[1]["title"] == "腾讯回购股份"
    assert result[1]["published_at"] is None
    for item in result:
        assert item["source"] in ("财联社", "新浪财经")
        assert "collected_at" in item


async def test_fetch_news_deduplicates_by_url(provider: NeoDataProvider) -> None:
    mock_result_1 = {
        "data": {
            "docData": {
                "docRecall": [
                    {
                        "docList": [
                            {
                                "title": "腾讯发布Q1财报",
                                "source": "财联社",
                                "url": "https://example.com/1",
                                "content": "内容1",
                                "publishTime": 1748736000,
                            }
                        ]
                    }
                ]
            }
        }
    }
    mock_result_2 = {
        "data": {
            "docData": {
                "docRecall": [
                    {
                        "docList": [
                            {
                                "title": "腾讯发布Q1财报(转载)",
                                "source": "新浪财经",
                                "url": "https://example.com/1",
                                "content": "内容2",
                                "publishTime": 1748736000,
                            }
                        ]
                    }
                ]
            }
        }
    }

    mock_query = AsyncMock(side_effect=[mock_result_1, mock_result_2])
    _inject_query(provider, mock_query)

    result = await provider.fetch_news(symbols=["00700.HK", "TCEHY.US"])

    assert len(result) == 1
    assert result[0]["title"] == "腾讯发布Q1财报"


async def test_fetch_news_handles_missing_symbols(provider: NeoDataProvider) -> None:
    assert await provider.fetch_news(symbols=None) == []

    mock_query = AsyncMock(return_value=None)
    _inject_query(provider, mock_query)

    result = await provider.fetch_news(symbols=["00700.HK"])
    assert result == []
