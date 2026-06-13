"""WeStockProvider 板块方法测试：board_sectors / hot_sectors。

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
# board_sectors (板块首页：行业/概念涨幅榜 + 行业资金流入 Top5)
# ═══════════════════════════════════════════════════════════════════


async def test_board_sectors_success(provider: WeStockProvider) -> None:
    """3 张表都返回数据 → 合并为统一 list，按 sector_type 分类。"""
    # 行业涨幅表
    industry_table = (
        "| name | changePct | turnoverRate | changePct5d | changePct20d | leadStock |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| 航天装备Ⅱ | 6.97 | 4.65 | 8.62 | -21.33 | 中天火箭(10.01) |\n"
        "| 数字媒体 | 3.13 | 5.01 | 2.51 | -7.39 | 凡拓数创(10.84) |\n"
    )
    # 概念涨幅表
    concept_table = (
        "| name | changePct | turnoverRate | changePct5d | changePct20d | leadStock |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| 机器人执行器概念 | 5.34 | 5.58 | 6.58 | 0.46 | 步科股份(11.35) |\n"
    )
    # 行业资金流入 Top5 表
    fund_flow_table = (
        "| name | changePct | mainNetInflow | mainNetInflow5d | upDownRatio |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 航天装备Ⅱ | 6.97 | 183129.01 | 132289.06 | 8/9 |\n"
    )
    stdout = industry_table + "\n" + concept_table + "\n" + fund_flow_table
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.board_sectors()

    # 3 张表合计 4 行
    assert len(result) == 4
    # 行业应有 2 行
    industry = [r for r in result if r["sector_type"] == "industry"]
    assert len(industry) == 2
    assert industry[0]["name"] == "航天装备Ⅱ"
    assert industry[0]["change_pct"] == 6.97
    assert industry[0]["lead_stock"] == "中天火箭(10.01)"
    # 概念应有 1 行
    concept = [r for r in result if r["sector_type"] == "concept"]
    assert len(concept) == 1
    assert concept[0]["name"] == "机器人执行器概念"
    # 资金流入应有 1 行
    flow = [r for r in result if r["sector_type"] == "fund_flow"]
    assert len(flow) == 1
    assert flow[0]["main_net_inflow"] == 183129.01
    assert flow[0]["up_down_ratio"] == "8/9"
    # 所有行带 source
    for r in result:
        assert r["source"] == "westock"


async def test_board_sectors_empty(provider: WeStockProvider) -> None:
    """CLI 返回空 → 列表为空。"""
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.board_sectors()
    assert result == []


async def test_board_sectors_error_returns_empty(provider: WeStockProvider) -> None:
    """CLI 错误（如 SKILL_006 重试后仍失败）→ 列表为空。"""
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="执行失败 [SKILL_006]: 查询热门板块首页失败\n",
            returncode=0,
        )
        result = await provider.board_sectors()
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# hot_sectors (热门板块)
# ═══════════════════════════════════════════════════════════════════


async def test_hot_sectors_success(provider: WeStockProvider) -> None:
    stdout = (
        "| index | level | symbol | rank | rankdelta | date | stock_type | name | zdf | zxj |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1351 | 0 | pt01801161 | 1 | 0 | 2026-06-06 17:50:00 | BK-HY-2 | 电力 | -3.50 | 3662.69 |\n"
        "| 845 | 0 | pt02003640 | 8 | 3 | 2026-06-06 17:50:00 | BK | 机器人概念 | 1.02 | 6707.21 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.hot_sectors(limit=10)

    assert len(result) == 2
    # 第 1 行: BK-HY-2 → industry
    assert result[0]["name"] == "电力"
    assert result[0]["symbol"] == "pt01801161"
    assert result[0]["sector_type"] == "industry"
    assert result[0]["change_pct"] == -3.50
    assert result[0]["zxj"] == 3662.69
    assert result[0]["rank"] == 1
    assert result[0]["date"] == "2026-06-06"  # 截取日期部分
    # 第 2 行: BK → concept
    assert result[1]["name"] == "机器人概念"
    assert result[1]["sector_type"] == "concept"


async def test_hot_sectors_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.hot_sectors()
    assert result == []


async def test_hot_sectors_error_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="数据为空，未找到匹配数据\n", returncode=0
        )
        result = await provider.hot_sectors()
    assert result == []
