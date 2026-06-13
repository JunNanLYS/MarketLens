"""WeStockProvider ipo + exdiv 日历方法测试。

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
        params={"command": "westock-data-clawhub"},
    )


# ═══════════════════════════════════════════════════════════════════
# ipo_calendar (新股日历)
# ═══════════════════════════════════════════════════════════════════


async def test_ipo_calendar_hk_success(provider: WeStockProvider) -> None:
    """港股新股日历 → event_type=ipo / market=hk。"""
    stdout = (
        "| stage | code | name | price | sgrq | ssrq | hy |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 今日申购 | 06658 | 溜溜梅 | 43.58~43.58 | 2026-06-05~2026-06-10 | 2026-06-15 | 包装食品 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.ipo_calendar("hk")

    assert len(result) == 1
    assert result[0]["event_type"] == "ipo"
    assert result[0]["market"] == "hk"
    assert result[0]["symbol"] == "06658"
    assert result[0]["name"] == "溜溜梅"
    assert result[0]["stage"] == "今日申购"
    assert result[0]["event_date"] == "2026-06-05~2026-06-10"  # sgrq 优先
    assert result[0]["source"] == "westock"


async def test_ipo_calendar_us_success(provider: WeStockProvider) -> None:
    """美股 IPO 日历。"""
    stdout = (
        "| code | name | listingDate | priceRange | offerPrice | status | industry | underwriter |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| GVSE-US | Gameverse Interactive Corp. | 2026-06-06 |  |  | In Registration | Packaged Software | Revere Securities LLC |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.ipo_calendar("us")

    assert len(result) == 1
    assert result[0]["market"] == "us"
    assert result[0]["symbol"] == "GVSE-US"
    assert result[0]["name"] == "Gameverse Interactive Corp."
    assert result[0]["stage"] == "In Registration"  # status 字段
    assert result[0]["event_date"] == "2026-06-06"  # listingDate


async def test_ipo_calendar_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.ipo_calendar("hk")
    assert result == []


async def test_ipo_calendar_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [SKILL_006_2]: 查询新股日历失败：bad param\n",
            returncode=0,
        )
        result = await provider.ipo_calendar("cn")
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# exdiv_calendar (除权日历)
# ═══════════════════════════════════════════════════════════════════


async def test_exdiv_calendar_hk_success(provider: WeStockProvider) -> None:
    """港股 exdiv（腾讯）。"""
    stdout = (
        "| code | name | exDivDate | payDate | reportEndDate | dividendPerShare | currency | dividendPlan |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| hk00700 | 腾讯控股 | 20260515 |  | 20251231 | 0 | USD | 末期息5.3港元; |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.exdiv_calendar("hk00700")

    assert len(result) == 1
    assert result[0]["event_type"] == "exdiv"
    assert result[0]["market"] == "hk"
    assert result[0]["symbol"] == "hk00700"
    assert result[0]["name"] == "腾讯控股"
    assert result[0]["ex_div_date"] == "20260515"
    assert result[0]["report_end_date"] == "20251231"
    assert result[0]["dividend_per_share"] == 0.0
    assert result[0]["currency"] == "USD"
    assert result[0]["dividend_plan"] == "末期息5.3港元;"


async def test_exdiv_calendar_us_success(provider: WeStockProvider) -> None:
    """美股 exdiv（苹果）。"""
    stdout = (
        "| code | name | exDivDate | payDate | reportEndDate | dividendPerShare | currency | dividendPlan |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| usAAPL | 苹果 | 20260511 | 20260514 |  | 0 | USD | 每股分配0.270000.2(USD) |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.exdiv_calendar("usAAPL")

    assert len(result) == 1
    assert result[0]["market"] == "us"
    assert result[0]["symbol"] == "usAAPL"
    assert result[0]["ex_div_date"] == "20260511"
    assert result[0]["pay_date"] == "20260514"


async def test_exdiv_calendar_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.exdiv_calendar("hk00700")
    assert result == []


async def test_exdiv_calendar_a_share_returns_empty(provider: WeStockProvider) -> None:
    """A 股 exdiv 数据源死 → 返回空（前端无感知）。"""
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [EXDIV_001]: 获取A股分红除权日数据失败：未找到数据\n",
            returncode=0,
        )
        result = await provider.exdiv_calendar("sh600519")
    assert result == []
