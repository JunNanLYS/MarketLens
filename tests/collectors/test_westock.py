import subprocess
from unittest.mock import MagicMock, patch

import pytest
from backend.collectors.westock import (
    WeStockProvider,
    _parse_markdown_tables,
    _detect_error,
    _try_number,
)


# ── 工具函数单测 ──────────────────────────────────────────────


async def test_parse_single_table() -> None:
    text = (
        "| code | name | type |\n"
        "| --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | GP-A |\n"
        "| sz000001 | 平安银行 | GP-A |\n"
    )
    tables = _parse_markdown_tables(text)
    assert len(tables) == 1
    assert len(tables[0]) == 2
    assert tables[0][0] == {"code": "sh600519", "name": "贵州茅台", "type": "GP-A"}


async def test_parse_multiple_tables() -> None:
    text = (
        "**lrb**\n\n"
        "| BasicEPS | EndDate | OperatingRevenue |\n"
        "| --- | --- | --- |\n"
        "| 65.66 | 2025-12-31 | 168838102514.79 |\n\n"
        "**zcfz**\n\n"
        "| TotalAssets | TotalLiability | SEWithoutMI |\n"
        "| --- | --- | --- |\n"
        "| 303834844021 | 49875590112 | 244637811032 |\n\n"
        "**xjll**\n\n"
        "| NetOperateCashFlow | EndDate |\n"
        "| --- | --- |\n"
        "| 61522204989 | 2025-12-31 |\n"
    )
    tables = _parse_markdown_tables(text)
    assert len(tables) == 3
    assert tables[0][0]["OperatingRevenue"] == "168838102514.79"
    assert tables[1][0]["TotalAssets"] == "303834844021"
    assert tables[2][0]["NetOperateCashFlow"] == "61522204989"


async def test_parse_dot_columns() -> None:
    text = (
        "| code | ma.MA_5 | macd.DIF | rsi.RSI_6 |\n"
        "| --- | --- | --- | --- |\n"
        "| sh600519 | 1297.59 | -28.80 | 49.59 |\n"
    )
    tables = _parse_markdown_tables(text)
    assert len(tables) == 1
    assert tables[0][0]["ma.MA_5"] == "1297.59"
    assert tables[0][0]["macd.DIF"] == "-28.80"


async def test_parse_empty_output() -> None:
    tables = _parse_markdown_tables("")
    assert tables == []


async def test_parse_mid_text_names() -> None:
    text = (
        "前面不是表格\n\n"
        "| code | name | type |\n"
        "| --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | GP-A |\n"
    )
    tables = _parse_markdown_tables(text)
    assert len(tables) == 1
    assert tables[0][0]["code"] == "sh600519"


async def test_detect_error_empty() -> None:
    assert _detect_error("数据为空") is not None


async def test_detect_error_unavailable() -> None:
    assert _detect_error('命令 "quote" 在当前渠道不可用') is not None


async def test_detect_error_skill_fail() -> None:
    err = _detect_error("执行失败 [SKILL_006]: 查询K线数据失败：未找到数据")
    assert err is not None


async def test_detect_no_error() -> None:
    assert _detect_error("| code | name |\n| --- | --- |\n| sh600519 | 茅台 |") is None


async def test_try_number_int() -> None:
    assert _try_number("123") == 123


async def test_try_number_float() -> None:
    assert _try_number("1309.60") == 1309.60


async def test_try_number_negative() -> None:
    assert _try_number("-28.80") == -28.80


async def test_try_number_string() -> None:
    assert _try_number("贵州茅台") == "贵州茅台"


async def test_try_number_empty() -> None:
    assert _try_number("") == ""


# ── Provider 单元测试 ────────────────────────────────────────


@pytest.fixture
async def provider() -> WeStockProvider:
    return WeStockProvider(
        name="westock",
        timeout=30,
        params={"command": "npx -y westock-data-clawhub@1.0.4"},
    )


async def test_init(provider: WeStockProvider) -> None:
    assert provider.name == "westock"
    assert provider.timeout == 30
    assert provider.command == "npx -y westock-data-clawhub@1.0.4"


async def test_init_default_command() -> None:
    p = WeStockProvider(name="westock_default")
    assert p.command == "npx -y westock-data-clawhub@1.0.4"


async def test_search_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n| sh600519 | 贵州茅台 | GP-A |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("茅台")
        assert len(result) == 1
        assert result[0]["code"] == "sh600519"
        assert result[0]["name"] == "贵州茅台"
        assert result[0]["type"] == "GP-A"


async def test_search_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.search("nosuch")
        assert result == []


async def test_quote_success(provider: WeStockProvider) -> None:
    stdout = (
        "| date | open | last | high | low | volume | amount | chg_rate | prev_close |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-06-01 | 1327 | 1309.60 | 1327 | 1301.31 | 43845 | 5741133268 | 0.35 | 1305.03 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.quote(["sh600519"])
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"
        assert result[0]["price"] == 1309.60
        assert result[0]["change_pct"] == 0.35
        assert result[0]["prev_close"] == 1305.03
        assert result[0]["change"] == pytest.approx(4.57)
        assert result[0]["source"] == "westock"
        assert "collected_at" in result[0]


async def test_quote_error_fallback(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.quote(["sh600519"])
        assert result == []


async def test_kline_success(provider: WeStockProvider) -> None:
    stdout = (
        "| date | open | last | high | low | volume | amount | chg_rate |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-06-01 | 1327 | 1309.60 | 1327 | 1301.31 | 43845 | 5741133268 | 0.35 |\n"
        "| 2026-05-29 | 1270.60 | 1326 | 1329 | 1270 | 76478 | 10037390000 | 0.61 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.kline("sh600519", "daily")
        assert len(result) == 2
        assert result[0]["close"] == 1309.60
        assert result[0]["change_pct"] == 0.35
        assert result[0]["source"] == "westock"
        assert result[1]["close"] == 1326
        mock_run.assert_called_once()


async def test_kline_weekly_period(provider: WeStockProvider) -> None:
    stdout = (
        "| date | open | last | high | low | volume | amount | chg_rate |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-05-25 | 1300 | 1310 | 1320 | 1290 | 100000 | 13000000 | 0.77 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        await provider.kline("sh600519", "weekly")
        # 验证使用了 'week' 而不是 'weekly'
        cmd_args = mock_run.call_args[0][0]
        assert "--period" in cmd_args
        period_idx = cmd_args.index("--period")
        assert cmd_args[period_idx + 1] == "week"


async def test_kline_monthly_period(provider: WeStockProvider) -> None:
    stdout = (
        "| date | open | last | high | low | volume | amount | chg_rate |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-05-01 | 1300 | 1310 | 1320 | 1290 | 100000 | 13000000 | 0.77 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        await provider.kline("sh600519", "monthly")
        cmd_args = mock_run.call_args[0][0]
        period_idx = cmd_args.index("--period")
        assert cmd_args[period_idx + 1] == "month"


async def test_finance_success(provider: WeStockProvider) -> None:
    stdout = (
        "**lrb**\n\n"
        "| BasicEPS | EndDate | NPParentCompanyOwners | OperatingCost | OperatingRevenue |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 65.66 | 2025-12-31 | 82320067101.68 | 14892277570.91 | 168838102514.79 |\n\n"
        "**zcfz**\n\n"
        "| TotalAssets | TotalLiability | SEWithoutMI |\n"
        "| --- | --- | --- |\n"
        "| 303834844021 | 49875590112 | 244637811032 |\n\n"
        "**xjll**\n\n"
        "| NetOperateCashFlow | EndDate |\n"
        "| --- | --- |\n"
        "| 61522204989 | 2025-12-31 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.finance("sh600519")
        assert result["symbol"] == "sh600519"
        assert result["revenue"] == 168838102514.79
        assert result["net_profit"] == 82320067101.68
        assert result["eps"] == 65.66
        assert result["report_period"] == "2025-12-31"
        assert result["gross_margin"] is not None
        assert result["net_margin"] is not None
        assert result["roe"] is not None
        assert result["debt_ratio"] is not None
        assert result["source"] == "westock"


async def test_fund_flow_asfund(provider: WeStockProvider) -> None:
    stdout = (
        "| code | EndDate | MainNetFlow | JumboNetFlow | BlockNetFlow | MidNetFlow | SmallNetFlow | MainInflowCircRate |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 2026-06-01 | -189981349.00 | 100236788.00 | -290218138.00 | 190296011.00 | -314662.00 | 0.01 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.fund_flow("sh600519")
        assert result["main_net_inflow"] == -189981349.0
        assert result["super_large_net_inflow"] == 100236788.0
        assert result["large_net_inflow"] == -290218138.0
        assert result["net_inflow_ratio"] == 0.01
        assert result["date"] == "2026-06-01"
        assert result["source"] == "westock"


async def test_fund_flow_hk(provider: WeStockProvider) -> None:
    stdout = (
        "| code | EndDate | MainNetFlow |\n"
        "| --- | --- | --- |\n"
        "| hk00700 | 2026-06-01 | 50000000 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.fund_flow("hk00700")
        assert result["main_net_inflow"] == 50000000
        # 验证使用了 hkfund 不是 asfund
        cmd_args = mock_run.call_args[0][0]
        assert "hkfund" in cmd_args


async def test_technical_success(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | date | closePrice | ma.MA_5 | ma.MA_10 | ma.MA_20 | ma.MA_60 | macd.DIF | macd.DEA | macd.MACD | rsi.RSI_6 | rsi.RSI_12 | boll.BOLL_UPPER | boll.BOLL_MID | boll.BOLL_LOWER |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| sh600519 | 贵州茅台 | 2026-06-01 | 1309.60 | 1297.59 | 1301.43 | 1328.81 | 1395.89 | -28.80 | -30.38 | 3.16 | 49.59 | 42.74 | 1395.08 | 1328.81 | 1262.55 |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.technical("sh600519")
        assert result["symbol"] == "sh600519"
        assert result["ma5"] == 1297.59
        assert result["ma20"] == 1328.81
        assert result["ma60"] == 1395.89
        assert result["macd_dif"] == -28.80
        assert result["macd_dea"] == -30.38
        assert result["macd_histogram"] == 3.16
        assert result["rsi6"] == 49.59
        assert result["rsi14"] == 42.74
        assert result["boll_upper"] == 1395.08
        assert result["boll_middle"] == 1328.81
        assert result["boll_lower"] == 1262.55
        assert result["source"] == "westock"


# ── 错误处理测试 ──────────────────────────────────────────────


async def test_run_cli_timeout_returns_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        assert await provider.search("茅台") == []
        assert await provider.quote(["sh600519"]) == []
        assert await provider.kline("sh600519") == []
        assert await provider.finance("sh600519") == {}
        assert await provider.fund_flow("sh600519") == {}
        assert await provider.technical("sh600519") == {}


async def test_run_cli_called_process_error(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "test", stderr="error")
        assert await provider.search("茅台") == []
        assert await provider.quote(["sh600519"]) == []


async def test_run_cli_data_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        assert await provider.search("茅台") == []
        assert await provider.finance("sh600519") == {}


async def test_run_cli_nonzero_exit(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="some error", returncode=1)
        assert await provider.search("茅台") == []
        assert await provider.finance("sh600519") == {}


async def test_run_cli_generic_exception(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("file not found")
        assert await provider.search("茅台") == []
        assert await provider.finance("sh600519") == {}


# ── 边界条件 ──────────────────────────────────────────────────


async def test_fund_flow_cmd_a_share() -> None:
    assert WeStockProvider._fund_flow_cmd("sh600519") == "asfund"
    assert WeStockProvider._fund_flow_cmd("sz000001") == "asfund"
    assert WeStockProvider._fund_flow_cmd("bj430047") == "asfund"


async def test_fund_flow_cmd_hk() -> None:
    assert WeStockProvider._fund_flow_cmd("hk00700") == "hkfund"


async def test_fund_flow_cmd_us() -> None:
    assert WeStockProvider._fund_flow_cmd("usAAPL") == "usfund"


async def test_fund_flow_cmd_unknown() -> None:
    assert WeStockProvider._fund_flow_cmd("xx12345") == "asfund"


async def test_quote_empty_table(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = await provider.quote(["sh600519"])
        assert result == []


async def test_finance_empty_tables(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="数据为空", returncode=0)
        result = await provider.finance("sh600519")
        assert result == {}


async def test_search_multiple_results(provider: WeStockProvider) -> None:
    stdout = (
        "| code | name | type |\n"
        "| --- | --- | --- |\n"
        "| sz000858 | 五粮液 | GP-A |\n"
        "| sh600809 | 山西汾酒 | GP-A |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("酒")
        assert len(result) == 2
        assert result[0]["code"] == "sz000858"
        assert result[1]["code"] == "sh600809"


# fetch_news tests


async def test_fetch_news_success(provider: WeStockProvider) -> None:
    lines = [
        "| news_id | news_title | rank | publish_time | source |",
        "| --- | --- | --- | --- | --- |",
        "| SN01 | headline1 | 1 | 1780312451 | src1 |",
        "| SN02 | headline2 | 10 | 1780312451 | src2 |",
        "| SN03 | headline3 | 99 | 1780312451 | src3 |",
    ]
    stdout = chr(10).join(lines)
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.fetch_news()
        assert len(result) == 3
        assert result[0]["title"] == "headline1"
        assert result[0]["importance"] == "high"
        assert result[1]["importance"] == "normal"
        assert result[2]["importance"] == "low"
        assert result[0]["url"] == "wehot://SN01"
        assert result[0]["published_at"] is not None


async def test_fetch_news_empty(provider: WeStockProvider) -> None:
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="data empty", returncode=0)
        result = await provider.fetch_news()
        assert result == []


async def test_fetch_news_no_news_id(provider: WeStockProvider) -> None:
    lines = [
        "| news_id | news_title | rank | publish_time | source |",
        "| --- | --- | --- | --- | --- |",
        "|  | noid | 1 | 1780312451 | src |",
    ]
    stdout = chr(10).join(lines)
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.fetch_news()
        assert len(result) == 1
        assert result[0]["url"] is None
