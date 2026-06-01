from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.collectors.sina import SinaProvider


@pytest.fixture
def provider() -> SinaProvider:
    return SinaProvider(
        name="sina",
        timeout=15,
        params={"quote_url": "https://hq.sinajs.cn/list={codes}"},
    )


def test_init(provider: SinaProvider) -> None:
    assert provider.name == "sina"
    assert provider.timeout == 15
    assert provider.quote_url == "https://hq.sinajs.cn/list={codes}"
    assert provider.optional is False


def test_to_sina_code_sh() -> None:
    assert SinaProvider._to_sina_code("600519") == "sh600519"


def test_to_sina_code_sz() -> None:
    assert SinaProvider._to_sina_code("000001") == "sz000001"


def test_to_sina_code_sz3() -> None:
    assert SinaProvider._to_sina_code("300001") == "sz300001"


def test_to_sina_code_already_prefixed() -> None:
    assert SinaProvider._to_sina_code("sh600519") == "sh600519"
    assert SinaProvider._to_sina_code("sz000001") == "sz000001"


def test_quote_success(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1800.00,1790.00,1810.00,1820.00,1795.00,'
        '1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,'
        '3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,'
        "2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00\";"
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.collectors.sina.httpx.get", return_value=mock_resp):
        result = provider.quote(["sh600519"])
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"
        assert result[0]["price"] == 1810.0
        assert result[0]["open"] == 1800.0
        assert result[0]["prev_close"] == 1790.0
        assert result[0]["source"] == "sina"
        assert "collected_at" in result[0]


def test_quote_change_calculation(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1790.00,1790.00,1800.00,1810.00,1785.00,'
        '1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,'
        '3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,'
        "2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00\";"
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.collectors.sina.httpx.get", return_value=mock_resp):
        result = provider.quote(["sh600519"])
        assert len(result) == 1
        assert result[0]["change"] == 10.0
        assert result[0]["change_pct"] == round(10.0 / 1790.0 * 100, 2)
        assert result[0]["amplitude"] == round(25.0 / 1790.0 * 100, 2)


def test_quote_multiple_symbols(provider: SinaProvider) -> None:
    sina_response = (
        'var hq_str_sh600519="贵州茅台,1800.00,1790.00,1810.00,1820.00,1795.00,'
        '1805.00,1806.00,50000,90000000.00,1000,1805.00,2000,1806.00,'
        '3000,1807.00,4000,1808.00,5000,1809.00,6000,1810.00,'
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";\n'
        'var hq_str_sz000001="平安银行,12.00,11.90,12.10,12.20,11.95,'
        '12.05,12.06,100000,1200000.00,500,12.05,600,12.06,'
        '700,12.07,800,12.08,900,12.09,1000,12.10,'
        '2026-05-30,15:00:00,00,0.00,0.00,0.00,0.00,0.00,0.00,0.00\";'
    )
    mock_resp = MagicMock()
    mock_resp.text = sina_response
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.collectors.sina.httpx.get", return_value=mock_resp):
        result = provider.quote(["sh600519", "sz000001"])
        assert len(result) == 2


def test_quote_timeout_returns_empty(provider: SinaProvider) -> None:
    with patch("backend.collectors.sina.httpx.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timeout")
        result = provider.quote(["sh600519"])
        assert result == []


def test_quote_http_error_returns_empty(provider: SinaProvider) -> None:
    with patch("backend.collectors.sina.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )
        result = provider.quote(["sh600519"])
        assert result == []


def test_quote_generic_exception_returns_empty(provider: SinaProvider) -> None:
    with patch("backend.collectors.sina.httpx.get") as mock_get:
        mock_get.side_effect = ConnectionError("network error")
        result = provider.quote(["sh600519"])
        assert result == []


def test_quote_empty_symbols(provider: SinaProvider) -> None:
    result = provider.quote([])
    assert result == []


def test_search_returns_empty(provider: SinaProvider) -> None:
    assert provider.search("茅台") == []


def test_kline_returns_empty(provider: SinaProvider) -> None:
    assert provider.kline("sh600519") == []


def test_finance_returns_empty(provider: SinaProvider) -> None:
    assert provider.finance("sh600519") == {}


def test_fund_flow_returns_empty(provider: SinaProvider) -> None:
    assert provider.fund_flow("sh600519") == {}


def test_technical_returns_empty(provider: SinaProvider) -> None:
    assert provider.technical("sh600519") == {}
