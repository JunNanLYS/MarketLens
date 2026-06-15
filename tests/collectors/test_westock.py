import subprocess
from unittest.mock import MagicMock, patch

import pytest
from backend.collectors.westock import (
    WeStockProvider,
    WESTOCK_NODE_ABORT,
    _parse_markdown_tables,
    _detect_error,
    _detect_node_abort,
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


async def test_detect_node_abort_csprng() -> None:
    """Node CSPRNG 断言失败:这次任务里复现的 rc=134 实际堆栈。"""
    stderr = (
        "\n  #  C:\\WINDOWS\\system32\\cmd.exe [1844]: std::shared_ptr<...> "
        "node::InitializeOncePerProcessInternal(...) at src\\node.cc:1225\n"
        "  #  Assertion failed: ncrypto::CSPRNG(nullptr, 0)\n"
        "\n----- Native stack trace -----\n"
    )
    out = _detect_node_abort(stderr)
    assert out is not None
    # _run_cli 用 error_code (WESTOCK_NODE_ABORT) + 触发短语拼接 last_err;
    # 这里直接断言常量,确保日志里看到的就是这个枚举值（不是 EMPTY_OUTPUT）。
    assert WESTOCK_NODE_ABORT == "WESTOCK_NODE_ABORT"


async def test_detect_node_abort_empty() -> None:
    assert _detect_node_abort("") is None
    assert _detect_node_abort(None) is None  # type: ignore[arg-type]
    # 测试 fixture 偶发传 MagicMock（模拟 subprocess stderr 副作用对象）,
    # 不应触发正则匹配崩溃。
    from unittest.mock import MagicMock

    assert _detect_node_abort(MagicMock()) is None


async def test_detect_node_abort_unrelated_stderr() -> None:
    """stderr 存在但不是 Node 崩溃:必须返回 None（不误报）。"""
    assert _detect_node_abort("Warning: experimental flag") is None
    assert _detect_node_abort("node version: v20.10.0") is None


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
        params={"command": "westock-data-clawhub"},
    )


async def test_init(provider: WeStockProvider) -> None:
    assert provider.name == "westock"
    assert provider.timeout == 30
    assert provider.command == "westock-data-clawhub"


async def test_init_default_command() -> None:
    p = WeStockProvider(name="westock_default")
    assert p.command == "westock-data-clawhub"


async def test_search_success(provider: WeStockProvider) -> None:
    """search() 把 westock 的 code/name/type 映射成 symbol/market/asset_type。

    回归 r17 修复：原先只返回 code/name/type，AssetService.search_assets
    按 symbol 取不到值会静默丢弃全部结果（前端看到"未找到"）。
    """
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n| sh600519 | 贵州茅台 | GP-A |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("茅台")
        assert len(result) == 1
        assert result[0]["symbol"] == "sh600519"
        assert result[0]["name"] == "贵州茅台"
        assert result[0]["market"] == "sh"
        assert result[0]["asset_type"] == "stock"


async def test_search_returns_service_contract_fields(provider: WeStockProvider) -> None:
    """回归 r17：返回字段必须能被 AssetService.search_assets 消费。

    关键不变量：每条结果必须含 non-empty `symbol`（否则 asset_service 的
    `if sym and sym not in seen_symbols` 会静默丢弃整条结果）。
    """
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n"
        "| sz300750 | 宁德时代 | GP-A-CYB |\n"
        "| hk00700 | 腾讯控股 | GP |\n"
        "| usAAPL | 苹果 | GP-US |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("test")
    assert len(result) == 3
    symbols = {r["symbol"] for r in result}
    assert symbols == {"sz300750", "hk00700", "usAAPL"}
    # market 从 code 前缀正确推断（不依赖 westock 自身返回）
    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["sz300750"]["market"] == "sz"
    assert by_symbol["hk00700"]["market"] == "hk"
    assert by_symbol["usAAPL"]["market"] == "us"
    # asset_type: GP* 全部 → stock
    for r in result:
        assert r["asset_type"] == "stock"


async def test_search_sector_type_maps_to_sector(provider: WeStockProvider) -> None:
    """westock 的 BK* type（板块/概念）→ asset_type='sector'，与 GP* 区分。"""
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n"
        "| pt01801081 | 华为概念 | BK |\n"
        "| sh600519 | 贵州茅台 | GP-A |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("test")
    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["pt01801081"]["asset_type"] == "sector"
    assert by_symbol["sh600519"]["asset_type"] == "stock"
    # 板块条目无市场前缀时 market 兜底为 "us"（与 SinaProvider 行为一致）
    assert by_symbol["pt01801081"]["market"] == "us"


async def test_search_skips_empty_code(provider: WeStockProvider) -> None:
    """westock 偶发返回 code 为空的行（表格解析兜底）→ 跳过。"""
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n"
        "|  |  |  |\n"
        "| sh600519 | 贵州茅台 | GP-A |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("test")
    assert len(result) == 1
    assert result[0]["symbol"] == "sh600519"


async def test_search_maps_all_westock_type_prefixes(provider: WeStockProvider) -> None:
    """回归 r17 P1: westock 所有实测 type 前缀必须映射到前端 ASSET_TYPES。

    覆盖 westock 实际出现的 type 枚举:
    - GP-ETF / ETF → etf (复盖 GP* 兜底前先判)
    - LOF → fund
    - ZS / ZS-ZQ → index
    - ZQ-NHG → bond
    - BK → sector
    - GP / GP-A / GP-A-CYB → stock
    """
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n"
        "| sh510300 | 沪深300ETF华泰柏瑞 | ETF |\n"
        "| usASHR.AM | 沪深300ETF-德银嘉实 | GP-ETF |\n"
        "| sz160706 | 沪深300LOF | LOF |\n"
        "| sh000300 | 沪深300 | ZS |\n"
        "| sh000012 | 国债指数 | ZS-ZQ |\n"
        "| sh204001 | GC001 | ZQ-NHG |\n"
        "| pt01801081 | 华为概念 | BK |\n"
        "| sh600519 | 贵州茅台 | GP-A |\n"
        "| sz300750 | 宁德时代 | GP-A-CYB |\n"
        "| hk00700 | 腾讯控股 | GP |\n"
        "| usAAPL | 苹果 | GP-US |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("test")
    by_symbol = {r["symbol"]: r for r in result}
    # 关键不变量: 任何前端的 9 类 asset_type 都能命中
    expected = {
        "sh510300": "etf",
        "usASHR.AM": "etf",   # GP-ETF 不被 GP* 截胡
        "sz160706": "fund",   # LOF
        "sh000300": "index",  # ZS
        "sh000012": "index",  # ZS-ZQ
        "sh204001": "bond",   # ZQ-NHG
        "pt01801081": "sector",  # BK
        "sh600519": "stock",  # GP-A
        "sz300750": "stock",  # GP-A-CYB
        "hk00700": "stock",   # GP
        "usAAPL": "stock",    # GP-US
    }
    actual = {sym: r["asset_type"] for sym, r in by_symbol.items()}
    assert actual == expected, f"asset_type 映射偏差: {actual}"


def test_westock_type_to_asset_type_unit() -> None:
    """纯函数: _westock_type_to_asset_type 各分支命中表（无 subprocess 依赖）。"""
    cases = [
        # 股票类
        ("", "stock"),
        ("GP", "stock"),
        ("GP-A", "stock"),
        ("GP-A-CYB", "stock"),
        ("GP-HK", "stock"),
        ("GP-US", "stock"),
        # ETF (必须先于 GP* 兜底)
        ("GP-ETF", "etf"),
        ("ETF", "etf"),
        ("QDII-ETF", "etf"),
        ("QDII-LOF", "etf"),
        # 基金 (LOF)
        ("LOF", "fund"),
        # 指数
        ("ZS", "index"),
        ("ZS-ZQ", "index"),
        # 债券
        ("ZQ", "bond"),
        ("ZQ-NHG", "bond"),
        # 板块
        ("BK", "sector"),
        ("BK-HY-2", "sector"),
        # 未知 → 兜底
        ("UNKNOWN-TYPE", "stock"),
    ]
    for wtype, expected in cases:
        assert WeStockProvider._westock_type_to_asset_type(wtype) == expected, (
            f"_westock_type_to_asset_type({wtype!r}) "
            f"应返回 {expected!r}, 实际 {WeStockProvider._westock_type_to_asset_type(wtype)!r}"
        )


async def test_search_returns_real_world_xiaomi_results(provider: WeStockProvider) -> None:
    """回归用户原始 bug 报告: search('小米') 必须返回 4 条可被前端消费的候选。

    真实 westock 输出（2026-06-15 实测）: hk01810 / hk81810 / usXIACY.PS / usXIACF.PS,
    全部 GP* → stock; market 从 code 前缀正确推断为 hk / us。
    """
    stdout = (
        "| code | name | type |\n| --- | --- | --- |\n"
        "| hk01810 | 小米集团-W | GP |\n"
        "| hk81810 | 小米集团-WR | GP |\n"
        "| usXIACY.PS | 小米集团(ADR) | GP |\n"
        "| usXIACF.PS | 小米集团 | GP |\n"
    )
    with patch("backend.collectors.westock.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
        result = await provider.search("小米")
    assert len(result) == 4
    # 关键不变量: 每条都必须有 non-empty symbol（AssetService.search_assets 按 symbol 取值）
    for r in result:
        assert r["symbol"], f"symbol 为空,会被 service 静默丢弃: {r}"
        assert r["market"] in ("hk", "us")
        assert r["asset_type"] == "stock"


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
        # 验证使用了 'week' 而不是 'weekly'。2026-06-13 变更：westock 走
        # PowerShell 调，参数在 -Command 后的字符串里。
        cmd_args = mock_run.call_args[0][0]
        ps_cmd = cmd_args[cmd_args.index("-Command") + 1]
        assert "--period" in ps_cmd
        assert "week" in ps_cmd
        assert "weekly" not in ps_cmd


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
        ps_cmd = cmd_args[cmd_args.index("-Command") + 1]
        assert "--period" in ps_cmd
        assert "month" in ps_cmd


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
        # 验证使用了 hkfund 不是 asfund（参数现在在 -Command 字符串里）
        cmd_args = mock_run.call_args[0][0]
        ps_cmd = cmd_args[cmd_args.index("-Command") + 1]
        assert "hkfund" in ps_cmd


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
        assert result[0]["symbol"] == "sz000858"
        assert result[0]["market"] == "sz"
        assert result[0]["asset_type"] == "stock"
        assert result[1]["symbol"] == "sh600809"


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
