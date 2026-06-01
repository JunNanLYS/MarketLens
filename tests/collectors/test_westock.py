import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from backend.collectors.westock import WeStockProvider


@pytest.fixture
def provider() -> WeStockProvider:
    return WeStockProvider(
        name="westock",
        timeout=30,
        params={"command": "npx -y westock-data-clawhub@1.0.4"},
    )


def test_init(provider: WeStockProvider) -> None:
    assert provider.name == "westock"
    assert provider.timeout == 30
    assert provider.command == "npx -y westock-data-clawhub@1.0.4"
    assert provider.optional is False


def test_init_default_command() -> None:
    p = WeStockProvider(name="westock_default")
    assert p.command == "npx -y westock-data-clawhub@1.0.4"


def test_search_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{"symbol": "sh600519", "name": "贵州茅台"}])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.search("茅台")
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"


def test_quote_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{
        "symbol": "sh600519",
        "price": 1800.0,
        "change": 10.0,
        "change_pct": 0.56,
        "open": 1790.0,
        "high": 1810.0,
        "low": 1785.0,
        "prev_close": 1790.0,
        "volume": 50000,
        "amount": 90000000,
        "amplitude": 1.4,
        "turnover_rate": 0.4,
        "high_52w": 1900.0,
        "low_52w": 1500.0,
    }])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.quote(["sh600519"])
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"
        assert result[0]["price"] == 1800.0
        assert result[0]["source"] == "westock"
        assert "collected_at" in result[0]


def test_kline_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{
        "symbol": "sh600519",
        "date": "2026-05-30",
        "open": 1790.0,
        "high": 1810.0,
        "low": 1785.0,
        "close": 1800.0,
        "volume": 50000,
        "amount": 90000000,
    }])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.kline("sh600519", "daily")
        assert len(result) == 1
        assert result[0]["source"] == "westock"


def test_finance_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{
        "symbol": "sh600519",
        "report_date": "2026-03-31",
        "revenue": 5000000000,
        "net_profit": 2500000000,
        "eps": 19.9,
        "period": "Q1",
    }])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.finance("sh600519")
        assert result["symbol"] == "sh600519"
        assert result["source"] == "westock"


def test_fund_flow_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{
        "symbol": "sh600519",
        "date": "2026-05-30",
        "main_inflow": 100000000,
        "main_outflow": 80000000,
        "net_flow": 20000000,
    }])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.fund_flow("sh600519")
        assert result["net_flow"] == 20000000
        assert result["source"] == "westock"


def test_technical_success(provider: WeStockProvider) -> None:
    mock_output = json.dumps([{
        "symbol": "sh600519",
        "date": "2026-05-30",
        "ma5": 1790.0,
        "ma20": 1780.0,
        "macd": 5.2,
        "rsi": 60.5,
        "boll_upper": 1850.0,
        "boll_lower": 1720.0,
    }])
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.technical("sh600519")
        assert result["rsi"] == 60.5
        assert result["source"] == "westock"


def test_timeout_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        assert provider.search("茅台") == []
        assert provider.quote(["sh600519"]) == []
        assert provider.kline("sh600519") == []
        assert provider.finance("sh600519") == {}
        assert provider.fund_flow("sh600519") == {}
        assert provider.technical("sh600519") == {}


def test_called_process_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "test", stderr="error")
        assert provider.search("茅台") == []
        assert provider.quote(["sh600519"]) == []


def test_json_decode_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="not json", returncode=0)
        assert provider.search("茅台") == []
        assert provider.quote(["sh600519"]) == []


def test_search_single_dict_result(provider: WeStockProvider) -> None:
    mock_output = json.dumps({"symbol": "sh600519", "name": "贵州茅台"})
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
        result = provider.search("茅台")
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"
