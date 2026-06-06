"""WeStockProvider 阶段 17 方法测试：chip / margintrade / blocktrade / lhb。

每组 3 段式：成功 / 空 / 异常
"""
import json
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
# chip_distribution (筹码成本)
# ═══════════════════════════════════════════════════════════════════

async def test_chip_distribution_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | closePrice | chipProfitRate | chipAvgCost | "
        "chipConcentration90 | chipConcentration70 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-05 | 1272.86 | 0.35 | 1418.42 | 7.79 | 4.16 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.chip_distribution("sh600519")
    assert result["symbol"] == "sh600519"
    assert result["date"] == "2026-06-05"
    assert result["close_price"] == 1272.86
    assert result["chip_profit_rate"] == 0.35
    assert result["chip_avg_cost"] == 1418.42
    assert result["chip_concentration_90"] == 7.79
    assert result["chip_concentration_70"] == 4.16


async def test_chip_distribution_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.chip_distribution("sh600519")
    assert result["symbol"] == "sh600519"
    assert "date" not in result or result.get("date") == ""


async def test_chip_distribution_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.chip_distribution("sh600519")
    assert result["symbol"] == "sh600519"


# ═══════════════════════════════════════════════════════════════════
# margintrade (融资融券)
# ═══════════════════════════════════════════════════════════════════

async def test_margintrade_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | closePrice | changePct | FinanceValue | SecurityValue | "
        "FinanceBuyValue | FinanceRefundValue | TradingValue | TradingValueDif | "
        "FinanceValueDOD | SecurityValueDOD |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-05 | 1272.86 | 0.38 | 19747396126.00 | "
        "135559344.00 | 380121085.00 | 458805818.00 | 19882955470.00 | 19611836782.00 | "
        "-0.40 | -1.09 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.margintrade("sh600519")
    assert result["symbol"] == "sh600519"
    assert result["date"] == "2026-06-05"
    assert result["close_price"] == 1272.86
    assert result["finance_value"] == 19747396126.0
    assert result["security_value"] == 135559344.0
    assert result["finance_value_dod"] == -0.40


async def test_margintrade_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.margintrade("sh600519")
    assert result["symbol"] == "sh600519"


# ═══════════════════════════════════════════════════════════════════
# blocktrade (大宗交易)
# ═══════════════════════════════════════════════════════════════════

async def test_blocktrade_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | closePrice | changePct |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.blocktrade("sh600519", "2026-06-01")
    assert result["symbol"] == "sh600519"
    assert result["date"] == "2026-06-01"
    assert result["close_price"] == 1309.60
    assert result["change_pct"] == -1.24
    # 概览表，明细字段应为 None
    assert result["turnover_price"] is None
    assert result["buy_department"] is None


async def test_blocktrade_empty(provider: WeStockProvider) -> None:
    """空 stdout 触发 _detect_error("CLI 返回空输出") → blocktrade 返回 None。"""
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.blocktrade("sh600519", "2026-06-01")
    # 空 stdout 不是有效响应（_detect_error 会报错），blocktrade 返回 None
    assert result is None


async def test_blocktrade_error_returns_none(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [SKILL_006]: 查询股票大宗交易失败：未找到数据\n",
            returncode=0,
        )
        result = await provider.blocktrade("sh600519", "2026-06-01")
    assert result is None


async def test_blocktrade_with_detail_table(provider: WeStockProvider) -> None:
    """表 2 含明细（成交价 / 成交额 / 折溢率 / 买卖方向 / 营业部）应被解析入库。

    验证：turnover_value 合计 / turnover_price 首笔 / buy_department JSON 列表。
    """
    stdout = (
        "| code | name | date | closePrice | changePct |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 |\n"
        "\n"
        "| tradingType | buySalesDepartment | turnoverPrice | turnoverValue | discountRate |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 买 | 中信证券上海分公司 | 1280.00 | 5000000.00 | -2.26 |\n"
        "| 卖 | 国泰君安证券总部 | 1290.00 | 3000000.00 | -1.50 |\n"
        "| 买 | 华泰证券益田路 | 1285.00 | 2000000.00 | -1.88 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.blocktrade("sh600519", "2026-06-01")
    assert result["symbol"] == "sh600519"
    assert result["close_price"] == 1309.60
    # 合计 5M + 3M + 2M = 10M
    assert result["turnover_value"] == pytest.approx(10000000.0)
    # 首笔成交价
    assert result["turnover_price"] == 1280.00
    # 首笔折溢率
    assert result["close_discount_rate"] == pytest.approx(-2.26)
    # 营业部按方向分桶，序列化为 JSON 列表
    buy_dept = json.loads(result["buy_department"])
    sell_dept = json.loads(result["sell_department"])
    assert buy_dept == ["中信证券上海分公司", "华泰证券益田路"]
    assert sell_dept == ["国泰君安证券总部"]


async def test_blocktrade_detail_table_english_columns(provider: WeStockProvider) -> None:
    """表 2 用英文列名（direction / department / price / amount）也应被解析。"""
    stdout = (
        "| code | name | date | closePrice | changePct |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 |\n"
        "\n"
        "| direction | department | price | amount |\n"
        "| --- | --- | --- | --- |\n"
        "| BUY | BrokerA | 1280.00 | 5000000.00 |\n"
        "| SELL | BrokerB | 1290.00 | 3000000.00 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.blocktrade("sh600519", "2026-06-01")
    assert result["turnover_value"] == pytest.approx(8000000.0)
    assert json.loads(result["buy_department"]) == ["BrokerA"]
    assert json.loads(result["sell_department"]) == ["BrokerB"]


# ═══════════════════════════════════════════════════════════════════
# lhb (龙虎榜)
# ═══════════════════════════════════════════════════════════════════

async def test_lhb_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | closePrice | changePct | netBuyAmount |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 | 1234567.00 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.lhb("sh600519", "2026-06-01")
    assert result["symbol"] == "sh600519"
    assert result["date"] == "2026-06-01"
    assert result["close_price"] == 1309.60
    assert result["change_pct"] == -1.24
    assert result["net_buy_amount"] == 1234567.0


async def test_lhb_no_data_returns_none(provider: WeStockProvider) -> None:
    """当日无龙虎榜数据 → lhb 服务返回 '当日无龙虎榜数据' 文本，CLI 仍 0 exit。"""
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="当日无龙虎榜数据\n", returncode=0
        )
        result = await provider.lhb("sh600519", "2026-06-01")
    assert result is None


async def test_lhb_error_returns_none(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [SKILL_006]: 查询龙虎榜失败\n",
            returncode=0,
        )
        result = await provider.lhb("sh600519", "2026-06-01")
    assert result is None


async def test_lhb_with_detail_table(provider: WeStockProvider) -> None:
    """表 2 含营业部明细（tradingType / buySalesDepartment）应被分桶入库。"""
    stdout = (
        "| code | name | date | closePrice | changePct | netBuyAmount |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 | 1234567.00 |\n"
        "\n"
        "| tradingType | buySalesDepartment | buyAmount |\n"
        "| --- | --- | --- |\n"
        "| 买 | 中信证券上海分公司 | 5000000.00 |\n"
        "| 买 | 华泰证券益田路 | 3000000.00 |\n"
        "| 卖 | 国泰君安证券总部 | -2000000.00 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.lhb("sh600519", "2026-06-01")
    assert result["symbol"] == "sh600519"
    assert result["close_price"] == 1309.60
    assert result["net_buy_amount"] == 1234567.0
    buy_dept = json.loads(result["buy_department"])
    sell_dept = json.loads(result["sell_department"])
    assert buy_dept == ["中信证券上海分公司", "华泰证券益田路"]
    assert sell_dept == ["国泰君安证券总部"]


async def test_lhb_detail_amount_sign_inference(provider: WeStockProvider) -> None:
    """表 2 无 tradingType 但有 buyAmount 正负 → 用金额正负推断方向。"""
    stdout = (
        "| code | name | date | closePrice | changePct | netBuyAmount |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | -1.24 | 0 |\n"
        "\n"
        "| name | amount |\n"
        "| --- | --- |\n"
        "| BrokerA | 1000000.00 |\n"
        "| BrokerB | -500000.00 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.lhb("sh600519", "2026-06-01")
    assert json.loads(result["buy_department"]) == ["BrokerA"]
    assert json.loads(result["sell_department"]) == ["BrokerB"]
