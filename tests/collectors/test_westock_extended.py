"""WeStockProvider 扩展方法测试：minute / dividend / shareholder / reserve"""

from unittest.mock import MagicMock, patch

import pytest
from backend.collectors.westock import WeStockProvider


@pytest.fixture
async def provider() -> WeStockProvider:
    return WeStockProvider(
        name="westock",
        timeout=30,
        params={"command": "npx -y westock-data-clawhub@1.0.4"},
    )


# ═══════════════════════════════════════════════════════════════════
# minute (分时数据)
# ═══════════════════════════════════════════════════════════════════


async def test_minute_success(provider: WeStockProvider) -> None:
    stdout = (
        "| time | price | volume | avg_price |\n"
        "| --- | --- | --- | --- |\n"
        "| 09:30 | 380.0 | 1234567 | 380.0 |\n"
        "| 09:31 | 380.5 | 987654 | 380.2 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.minute("sh600519")
        assert len(result) == 2
        assert result[0]["time"] == "09:30"
        assert result[0]["price"] == 380.0
        assert result[0]["source"] == "westock"
        assert "collected_at" in result[0]


async def test_minute_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.minute("sh600519")
        assert result == []


async def test_minute_with_days(provider: WeStockProvider) -> None:
    stdout = (
        "| time | price | volume | avg_price |\n"
        "| --- | --- | --- | --- |\n"
        "| 09:30 | 380.0 | 1000 | 380.0 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.minute("sh600519", days=5)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════
# dividend (分红记录)
# ═══════════════════════════════════════════════════════════════════


async def test_dividend_success(provider: WeStockProvider) -> None:
    stdout = (
        "| ex_dividend_date | CashDiv | BonusShareRatio | recordDate | announceDate |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2025-06-15 | 1.5 | 0 | 2025-06-16 | 2025-05-20 |\n"
        "| 2024-06-10 | 1.2 | 0 | 2024-06-11 | 2024-05-18 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.dividend("sh600519")
        assert len(result) == 2
        assert result[0]["cash_dividend"] == 1.5
        assert result[0]["ex_date"] == "2025-06-15"
        assert result[0]["source"] == "westock"
        assert result[1]["cash_dividend"] == 1.2


async def test_dividend_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.dividend("sz000001")
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# shareholder (股东结构)
# ═══════════════════════════════════════════════════════════════════


async def test_shareholder_success(provider: WeStockProvider) -> None:
    """CLI 返回两个表格：十大股东 + 股东人数变化"""
    stdout_lines = [
        "| rank | HolderName | HoldAmount | HoldPercent |",
        "| --- | --- | --- | --- |",
        "| 1 | AAA | 700000000 | 58.0 |",
        "| 2 | BBB | 50000000 | 4.1 |",
        "",
        "| EndDate | HolderTotal | AvgShares |",
        "| --- | --- | --- |",
        "| 2025-12-31 | 150000 | 8000 |",
    ]
    stdout = chr(10).join(stdout_lines)
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.shareholder("sh600519")
        assert result["source"] == "westock"
        assert len(result["top_shareholders"]) == 2
        assert result["top_shareholders"][0]["name"] == "AAA"
        assert result["top_shareholders"][0]["ratio"] == 58.0
        assert len(result["holder_count_history"]) == 1
        assert result["holder_count_history"][0]["total_holders"] == 150000


async def test_shareholder_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.shareholder("sz000001")
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# reserve (业绩预告)
# ═══════════════════════════════════════════════════════════════════


async def test_reserve_success(provider: WeStockProvider) -> None:
    stdout = (
        "| ReportDate | ForcastType | NetProfitLow | NetProfitHigh | ChangeLow | ChangeHigh | Summary |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2025Q4 | 预增 | 500000000 | 550000000 | 20.0 | 32.0 | 业绩大幅增长 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.reserve("sh600519")
        assert result["forecast_type"] == "预增"
        assert result["profit_lower"] == 500000000
        assert result["profit_upper"] == 550000000
        assert result["change_lower"] == 20.0
        assert result["source"] == "westock"


async def test_reserve_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.reserve("sz000001")
        assert result["symbol"] == "sz000001"
        assert result["source"] == "westock"


# ═══════════════════════════════════════════════════════════════════
# 错误路径：CLI 超时等
# ═══════════════════════════════════════════════════════════════════


async def test_minute_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("npx not found")
        assert await provider.minute("sh600519") == []


async def test_dividend_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="error", returncode=1)
        assert await provider.dividend("sh600519") == []


async def test_shareholder_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("npx not found")
        assert await provider.shareholder("sh600519") == {}


async def test_reserve_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("npx not found")
        result = await provider.reserve("sh600519")
        assert result["symbol"] == "sh600519"
