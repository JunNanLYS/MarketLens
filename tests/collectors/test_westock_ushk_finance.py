"""WeStockProvider 港美股财务方法测试：us_finance / hk_finance。

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
# us_finance (美股财务)
# ═══════════════════════════════════════════════════════════════════


async def test_us_finance_income_success(provider: WeStockProvider) -> None:
    """美股 income 表 2 期数据 → period_type=quarter（_Q 后缀字段）。"""
    stdout = (
        "| _date | BasicEPS | Sales | NetIncome | EBITDA | EBIT | EndDate | SecuCode |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2025-12-31 | 1.85 | 102466.0 | 27466.0 | 35554.0 | 32427.0 | 2025-12-31 | usAAPL |\n"
        "| 2025-09-30 | 1.57 | 94036.0 | 23434.0 | 31032.0 | 28202.0 | 2025-09-30 | usAAPL |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.us_finance("usAAPL", ftype="income", num=2)

    assert len(result) == 2
    # period_type 推断: 字段无 _Q 后缀 → annual
    assert result[0]["period_type"] == "annual"
    assert result[0]["currency"] == "USD"
    assert result[0]["end_date"] == "2025-12-31"
    assert result[0]["basic_eps"] == 1.85
    assert result[0]["revenue"] == 102466.0
    assert result[0]["net_income"] == 27466.0
    assert result[0]["ebitda"] == 35554.0
    # period_mark 推导
    assert result[0]["period_mark"] == "2025FY"
    # 兜底
    assert "raw_json" in result[0]
    assert result[0]["source"] == "westock"


async def test_us_finance_quarter_success(provider: WeStockProvider) -> None:
    """美股含 _Q 字段 → period_type=quarter，period_mark=YYYYQn。"""
    stdout = (
        "| _date | BasicEPS_Q | Sales_Q | NetIncome_Q | EndDate | SecuCode |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| 2025-12-31 | 1.85 | 102466.0 | 27466.0 | 2025-12-31 | usAAPL |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.us_finance("usAAPL", ftype="income", num=1)

    assert result[0]["period_type"] == "quarter"
    assert result[0]["revenue"] == 102466.0  # 自动选 Sales_Q
    assert result[0]["period_mark"] == "2025Q4"


async def test_us_finance_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.us_finance("usAAPL")
    assert result == []


async def test_us_finance_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.us_finance("usAAPL")
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# hk_finance (港股财务)
# ═══════════════════════════════════════════════════════════════════


async def test_hk_finance_zhsy_success(provider: WeStockProvider) -> None:
    """港股 zhsy 表（综合损益表）含子行业/子产品分布。"""
    stdout = (
        "| _date | BasicEPS | OperatingRevenue | ProfitToShareholders | EndDate | ReportType | SecuCode |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2024-12-31 | 22.61 | 712989719408.72 | 209573020528.08 | 2024-12-31 | 年度报告 | hk00700 |\n"
        "| 2025-03-31 | 5.69 | 195076015710.40 | 51819945047.20 | 2025-03-31 | 第一季报 | hk00700 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.hk_finance("hk00700", ftype="zhsy", num=2)

    assert len(result) == 2
    # 第 1 行: 年度
    assert result[0]["period_type"] == "annual"
    assert result[0]["currency"] == "HKD"
    assert result[0]["end_date"] == "2024-12-31"
    assert result[0]["period_mark"] == "2024FY"
    assert result[0]["basic_eps"] == 22.61
    assert result[0]["revenue"] == 712989719408.72
    # 第 2 行: 第一季报 → quarter
    assert result[1]["period_type"] == "quarter"
    assert result[1]["period_mark"] == "2025Q1"
    assert result[1]["basic_eps"] == 5.69


async def test_hk_finance_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.hk_finance("hk00700")
    assert result == []


async def test_hk_finance_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [SKILL_006]: 查询港股财报失败\n",
            returncode=0,
        )
        result = await provider.hk_finance("hk00700")
    assert result == []
