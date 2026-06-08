"""WeStockProvider ETF 全套方法测试：etf_info / etf_holdings / etf_nav / etf_holders / etf_financial

每组 3 段式：成功 / 空 / 异常
"""

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
# etf_info (ETF 基本信息 + 行情)
# ═══════════════════════════════════════════════════════════════════


async def test_etf_info_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | etfType | trackIndexCode | trackIndexName | "
        "closePrice | changePct | totalMV | nav | return1Y | maxDrawdown1Y |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh510300 | 沪深300ETF | 2026-06-05 | ETF | sh000300 | 沪深300 | "
        "4.12 | 0.5 | 2000000000000 | 4.13 | 8.5 | -12.0 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.etf_info("sh510300")
    assert result["symbol"] == "sh510300"
    assert result["etf_type"] == "ETF"
    assert result["track_index_code"] == "sh000300"
    assert result["close_price"] == 4.12
    assert result["total_mv"] == 2000000000000
    assert result["return_1y"] == 8.5
    assert result["source"] == "westock"


async def test_etf_info_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.etf_info("sh000000")
    assert result["symbol"] == "sh000000"
    assert result["source"] == "westock"
    assert "collected_at" in result
    # 空数据时不应有 date 字段
    assert "date" not in result or result.get("date") == ""


async def test_etf_info_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.etf_info("invalid")
    assert result["symbol"] == "invalid"
    assert result["source"] == "westock"


# ═══════════════════════════════════════════════════════════════════
# etf_holdings (ETF 成分股)
# ═══════════════════════════════════════════════════════════════════


async def test_etf_holdings_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | ratio |\n"
        "| --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 5.2 |\n"
        "| sh601318 | 中国平安 | 3.8 |\n"
        "| sz000858 | 五粮液 | 2.5 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.etf_holdings("sh510300")
    assert len(result) == 3
    assert result[0]["constituent_code"] == "sh600519"
    assert result[0]["ratio"] == 5.2
    assert result[0]["source"] == "westock"


async def test_etf_holdings_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.etf_holdings("invalid")
    assert result == []


async def test_etf_holdings_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.etf_holdings("invalid")
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# etf_nav (ETF 历史净值)
# ═══════════════════════════════════════════════════════════════════


async def test_etf_nav_success(provider: WeStockProvider) -> None:
    stdout = (
        "| date | nav | navChange | navChangePct | accNav |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2026-06-05 | 4.13 | 0.02 | 0.49 | 1.25 |\n"
        "| 2026-06-04 | 4.11 | -0.01 | -0.24 | 1.24 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.etf_nav("sh510300", "2026-06-01", "2026-06-05")
    assert len(result) == 2
    assert result[0]["date"] == "2026-06-05"
    assert result[0]["nav"] == 4.13
    assert result[0]["nav_change_pct"] == 0.49
    assert result[0]["source"] == "westock"


async def test_etf_nav_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.etf_nav("invalid", "2026-01-01", "2026-01-31")
    assert result == []


async def test_etf_nav_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.etf_nav("invalid", "2026-01-01", "2026-01-31")
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# etf_holders (ETF 持有人结构)
# ═══════════════════════════════════════════════════════════════════


async def test_etf_holders_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | date | holderAccount | individualHolderShare | "
        "individualHolderRatio | institutionHolderShare | institutionHolderRatio | "
        "top10Share | top10Ratio |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh510300 | 2026-03-31 | 1000000 | 500000000 | 30.0 | "
        "1100000000 | 70.0 | 800000000 | 50.0 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.etf_holders("sh510300")
    assert result["symbol"] == "sh510300"
    assert result["report_date"] == "2026-03-31"
    assert result["holder_account"] == 1000000
    assert result["individual_holder_ratio"] == 30.0
    assert result["institution_holder_ratio"] == 70.0
    assert result["top10_ratio"] == 50.0


async def test_etf_holders_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.etf_holders("invalid")
    assert result["symbol"] == "invalid"
    assert "report_date" not in result or result.get("report_date") == ""


async def test_etf_holders_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.etf_holders("invalid")
    assert result["symbol"] == "invalid"


# ═══════════════════════════════════════════════════════════════════
# etf_financial (ETF 资产配置)
# ═══════════════════════════════════════════════════════════════════


async def test_etf_financial_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | date | totalAssets | stockRatio | bondRatio | "
        "commodityRatio | fundRatio | keyAssetRatio |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh510300 | 2026-03-31 | 200000000000 | 95.0 | 3.0 | 0.0 | 0.0 | 0.0 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.etf_financial("sh510300")
    assert result["symbol"] == "sh510300"
    assert result["date"] == "2026-03-31"
    assert result["total_assets"] == 200000000000
    assert result["stock_ratio"] == 95.0
    assert result["bond_ratio"] == 3.0


async def test_etf_financial_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.etf_financial("invalid")
    assert result["symbol"] == "invalid"
    assert "date" not in result or result.get("date") == ""


async def test_etf_financial_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.etf_financial("invalid")
    assert result["symbol"] == "invalid"
