"""端到端测试：westock 扩展方法 fetch → INSERT → SELECT 完整链路。

覆盖 `tests/services/test_westock_storage.py` 缺失的 13 个扩展方法（阶段 14-17）：
- ETF 5：etf_info / etf_holdings / etf_nav / etf_holders / etf_financial
- 事件 4：chip_distribution / margintrade / blocktrade / lhb
- 日历/财报 3：ipo_calendar / exdiv_calendar / us_finance
- 板块 2：board_sectors / hot_sectors（共用 sector_daily_quote 表）

测试目标：normalizer 输出键名 → row tuple 取值 → SQL INSERT 列名 三方映射一致。
单测覆盖 mock 层（test_westock_*.py），本文件覆盖"fetch → INSERT → SELECT"集成层。

不修任何生产代码；与现有 test_westock_storage.py 同模式（autouse fixture + 全栈 CollectionService）。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.collectors.westock import WeStockProvider
from backend.services.collection_service import CollectionService
from backend.storage.database import get_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


# ------------------------------------------------------------------
# Mock Provider —— 继承 WeStockProvider 让 _is_westock_only isinstance 通过
# super().__init__ 不带 params 时 __init__ 内部 _run_cli 不会真的执行
# （仅在 _run_cli 被调时才查 powershell 探测；本测试不调它）
# ------------------------------------------------------------------


class _WestockExtendedMockProvider(WeStockProvider):
    """为扩展方法提供固定返回值的 Mock provider。"""

    def __init__(self) -> None:
        super().__init__(name="westock")
        self.name = "westock"

    # ----- ETF 5 -----
    async def etf_info(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": "2026-06-10",
            "etf_type": "股票型",
            "establish_date": "2012-05-28",
            "track_index_code": "000300",
            "track_index_name": "沪深300",
            "manage_institution": "华泰柏瑞",
            "close_price": 3.92,
            "change_pct": 0.51,
            "total_mv": 1200000000000.0,
            "shares": 305000000000.0,
            "shares_chg": -1500000.0,
            "nav": 3.9012,
            "disc": 0.48,
            "ytd_return": 5.32,
            "return_1m": 1.2,
            "return_3m": 4.5,
            "return_6m": 8.1,
            "return_1y": 12.3,
            "return_3y": 25.6,
            "max_drawdown_1m": -2.1,
            "max_drawdown_3m": -5.4,
            "max_drawdown_6m": -8.0,
            "max_drawdown_1y": -10.2,
            "max_drawdown_3y": -22.5,
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    async def etf_holdings(self, symbol: str) -> list[dict]:
        return [
            {
                "symbol": symbol,
                "constituent_code": "sh600519",
                "constituent_name": "贵州茅台",
                "ratio": 5.5,
                "date": "2026-06-10",
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
            {
                "symbol": symbol,
                "constituent_code": "sz000858",
                "constituent_name": "五粮液",
                "ratio": 3.2,
                "date": "2026-06-10",
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
        ]

    async def etf_nav(
        self, symbol: str, start: str, end: str
    ) -> list[dict]:
        return [
            {
                "symbol": symbol,
                "date": "2026-06-09",
                "nav": 3.9012,
                "nav_change": 0.002,
                "nav_change_pct": 0.05,
                "acc_nav": 1.456,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
            {
                "symbol": symbol,
                "date": "2026-06-10",
                "nav": 3.9188,
                "nav_change": 0.0176,
                "nav_change_pct": 0.45,
                "acc_nav": 1.462,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
        ]

    async def etf_holders(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "report_date": "2026-03-31",
            "holder_account": 250000,
            "individual_holder_share": 800000000.0,
            "individual_holder_ratio": 65.5,
            "institution_holder_share": 420000000.0,
            "institution_holder_ratio": 34.5,
            "top10_share": 320000000.0,
            "top10_ratio": 26.3,
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    async def etf_financial(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "date": "2026-06-10",
            "total_assets": 1200000000000.0,
            "stock_ratio": 92.5,
            "bond_ratio": 4.5,
            "commodity_ratio": 0.0,
            "fund_ratio": 1.5,
            "key_asset_ratio": 1.5,
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    # ----- 事件 4 -----
    async def chip_distribution(self, symbol: str) -> dict | None:
        return {
            "symbol": symbol,
            "date": "2026-06-10",
            "close_price": 1800.0,
            "chip_profit_rate": 85.5,
            "chip_avg_cost": 1500.0,
            "chip_concentration_90": 35.2,
            "chip_concentration_70": 22.1,
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    async def margintrade(self, symbol: str) -> dict | None:
        return {
            "symbol": symbol,
            "date": "2026-06-10",
            "close_price": 1800.0,
            "change_pct": 1.5,
            "finance_value": 5000000000.0,
            "security_value": 80000000.0,
            "finance_buy_value": 120000000.0,
            "finance_refund_value": 100000000.0,
            "trading_value": 22000000.0,
            "trading_value_dif": 20000000.0,
            "finance_value_dod": 15000000.0,
            "security_value_dod": 200000.0,
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    async def blocktrade(self, symbol: str, date: str) -> dict | None:
        return {
            "symbol": symbol,
            "date": date,
            "close_price": 1800.0,
            "change_pct": -0.5,
            "turnover_price": 1780.0,
            "turnover_value": 35000000.0,
            "close_discount_rate": -1.11,
            "buy_department": json.dumps(
                ["机构专用席位", "中信证券上海分公司"], ensure_ascii=False
            ),
            "sell_department": json.dumps(
                ["华泰证券深圳益田路"], ensure_ascii=False
            ),
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    async def lhb(self, symbol: str, date: str) -> dict | None:
        return {
            "symbol": symbol,
            "date": date,
            "name": "贵州茅台",
            "close_price": 1800.0,
            "change_pct": 5.5,
            "net_buy_amount": 250000000.0,
            "buy_department": json.dumps(
                ["东方证券绍兴解放南路", "华鑫证券上海分公司"], ensure_ascii=False
            ),
            "sell_department": json.dumps(
                ["机构专用席位"], ensure_ascii=False
            ),
            "reason": "涨幅偏离值达7%的证券",
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }

    # ----- 日历/财报 3 -----
    async def ipo_calendar(self, market: str) -> list[dict]:
        return [
            {
                "event_type": "ipo",
                "event_date": "2026-06-15",
                "symbol": "hk00999",
                "name": "Example Corp",
                "market": market,
                "stage": "申购",
                "price": 10.5,
                "listing_date": "2026-06-20",
                "sgrq": "2026-06-15",
                "ssrq": "2026-06-20",
                "ex_div_date": None,
                "pay_date": None,
                "report_end_date": None,
                "dividend_per_share": None,
                "currency": "HKD",
                "dividend_plan": None,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            }
        ]

    async def exdiv_calendar(self, symbol: str) -> list[dict]:
        return [
            {
                "event_type": "exdiv",
                "event_date": "2026-06-20",
                "symbol": symbol,
                "name": "Tencent",
                "market": "hk",
                "stage": None,
                "price": None,
                "listing_date": None,
                "sgrq": None,
                "ssrq": None,
                "ex_div_date": "2026-06-20",
                "pay_date": "2026-07-05",
                "report_end_date": "2025-12-31",
                "dividend_per_share": 3.4,
                "currency": "HKD",
                "dividend_plan": "末期息",
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            }
        ]

    async def us_finance(
        self, symbol: str, ftype: str = "income", num: int = 4
    ) -> list[dict]:
        """按 ftype 分流：income/balance/cashflow 各自返回固定 1 期数据。

        3 个 ftype 共用同一 end_date（年报期 2024-12-31）——与真实 westock CLI
        一致；UNIQUE(symbol, end_date, period_type, source) 会让 2/3 被 IGNORE 跳过。
        test_us_finance_e2e 验证这一去重行为。
        """
        base = {
            "symbol": symbol,
            "end_date": "2024-12-31",
            "period_type": "annual",
            "period_mark": "2024FY",
            "source": "westock",
            "collected_at": "2026-06-10T00:00:00+00:00",
        }
        if ftype == "income":
            return [
                {
                    **base,
                    "currency": "USD",
                    "revenue": 391000000000.0,
                    "net_income": 95000000000.0,
                    "gross_profit": 170000000000.0,
                    "operating_income": 110000000000.0,
                    "ebitda": 130000000000.0,
                    "ebit": 110000000000.0,
                    "basic_eps": 6.11,
                    "diluted_eps": 6.08,
                    "total_assets": None,
                    "total_liabilities": None,
                    "total_equity": None,
                    "operating_cashflow": None,
                    "investing_cashflow": None,
                    "financing_cashflow": None,
                    "capex": None,
                    "raw_json": json.dumps({"ftype": "income", "value": 391}),
                }
            ]
        if ftype == "balance":
            return [
                {
                    **base,
                    "currency": "USD",
                    "revenue": None,
                    "net_income": None,
                    "gross_profit": None,
                    "operating_income": None,
                    "ebitda": None,
                    "ebit": None,
                    "basic_eps": None,
                    "diluted_eps": None,
                    "total_assets": 365000000000.0,
                    "total_liabilities": 308000000000.0,
                    "total_equity": 57000000000.0,
                    "operating_cashflow": None,
                    "investing_cashflow": None,
                    "financing_cashflow": None,
                    "capex": None,
                    "raw_json": json.dumps({"ftype": "balance"}),
                }
            ]
        # cashflow
        return [
            {
                **base,
                "currency": "USD",
                "revenue": None,
                "net_income": None,
                "gross_profit": None,
                "operating_income": None,
                "ebitda": None,
                "ebit": None,
                "basic_eps": None,
                "diluted_eps": None,
                "total_assets": None,
                "total_liabilities": None,
                "total_equity": None,
                "operating_cashflow": 110000000000.0,
                "investing_cashflow": -45000000000.0,
                "financing_cashflow": -65000000000.0,
                "capex": -12000000000.0,
                "raw_json": json.dumps({"ftype": "cashflow"}),
            }
        ]

    # ----- 板块 2 -----
    async def board_sectors(self) -> list[dict]:
        """返回 3 类：industry + concept + fund_flow 验证 UNIQUE(name, date, sector_type, source)。"""
        return [
            {
                "name": "白酒",
                "date": "2026-06-10",
                "sector_type": "industry",
                "symbol": None,
                "change_pct": 2.5,
                "turnover_rate": 1.8,
                "change_pct_5d": 5.2,
                "change_pct_20d": 8.1,
                "lead_stock": "贵州茅台",
                "main_net_inflow": 1500000000.0,
                "main_net_inflow_5d": 5000000000.0,
                "up_down_ratio": 3.5,
                "rank": None,
                "zxj": None,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
            {
                "name": "新能源",
                "date": "2026-06-10",
                "sector_type": "concept",
                "symbol": None,
                "change_pct": 3.2,
                "turnover_rate": 2.5,
                "change_pct_5d": 7.0,
                "change_pct_20d": 12.5,
                "lead_stock": "宁德时代",
                "main_net_inflow": 2000000000.0,
                "main_net_inflow_5d": 8000000000.0,
                "up_down_ratio": 4.2,
                "rank": None,
                "zxj": None,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
            {
                "name": "电子",
                "date": "2026-06-10",
                "sector_type": "fund_flow",
                "symbol": None,
                "change_pct": 1.5,
                "turnover_rate": 1.2,
                "change_pct_5d": 3.5,
                "change_pct_20d": 6.0,
                "lead_stock": None,
                "main_net_inflow": 800000000.0,
                "main_net_inflow_5d": 3000000000.0,
                "up_down_ratio": 2.5,
                "rank": None,
                "zxj": None,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            },
        ]

    async def hot_sectors(self, limit: int = 10) -> list[dict]:
        return [
            {
                "name": "锂电池",
                "date": "2026-06-10",
                "sector_type": "industry",
                "symbol": "BK0670",
                "change_pct": 5.5,
                "turnover_rate": None,
                "change_pct_5d": None,
                "change_pct_20d": None,
                "lead_stock": None,
                "main_net_inflow": None,
                "main_net_inflow_5d": None,
                "up_down_ratio": None,
                "rank": 1,
                "zxj": 1500.5,
                "source": "westock",
                "collected_at": "2026-06-10T00:00:00+00:00",
            }
        ]


# ------------------------------------------------------------------
# Fixture：与 test_westock_storage.py 同模式（autouse + 临时 db）
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def setup_test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def westock_service():
    return CollectionService(
        providers={
            "structured": [_WestockExtendedMockProvider()],
            "news": [],
        }
    )


# ------------------------------------------------------------------
# 13 个 e2e 测试
# ------------------------------------------------------------------


async def test_etf_info_e2e(westock_service: CollectionService) -> None:
    """ETF 基础信息：27 列至少覆盖 15 列 + 关键字段映射。

    27 列全字段落库 + UNIQUE 约束。仅断 ~6 列会漏掉 row tuple 大幅错位的 bug
    （如 establish_date 写到 manage_institution 列）；本测试覆盖 16 列。
    """
    result = await westock_service.collect_etf_info("sh510300")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM etf_basic WHERE code='sh510300'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    # 16 列覆盖：text / float / date / 周期 / 最大回撤
    assert row["code"] == "sh510300"
    assert row["date"] == "2026-06-10"
    assert row["etf_type"] == "股票型"
    assert row["establish_date"] == "2012-05-28"
    assert row["track_index_code"] == "000300"
    assert row["track_index_name"] == "沪深300"
    assert row["manage_institution"] == "华泰柏瑞"
    assert row["close_price"] == 3.92
    assert row["change_pct"] == 0.51
    assert row["shares"] == 305_000_000_000.0
    assert row["shares_chg"] == -1_500_000.0
    assert row["nav"] == 3.9012
    assert row["disc"] == 0.48
    assert row["ytd_return"] == 5.32
    assert row["return_1m"] == 1.2
    assert row["max_drawdown_1m"] == -2.1
    assert row["max_drawdown_3y"] == -22.5


async def test_etf_holdings_e2e(westock_service: CollectionService) -> None:
    """ETF 成分股：多行写入 + 顺序保留 + UNIQUE(code, constituent_code, date, source)。"""
    result = await westock_service.collect_etf_holdings("sh510300")
    assert result is not None
    assert len(result) == 2
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM etf_holdings WHERE code='sh510300' ORDER BY ratio DESC"
        ).fetchall()
    assert len(rows) == 2
    row = dict(rows[0])
    assert row["constituent_code"] == "sh600519"
    assert row["constituent_name"] == "贵州茅台"
    assert row["ratio"] == 5.5


async def test_etf_nav_e2e(westock_service: CollectionService) -> None:
    """ETF 净值：多行 + UNIQUE(code, date, source) 去重。"""
    result = await westock_service.collect_etf_nav(
        "sh510300", "2026-06-09", "2026-06-10"
    )
    assert result is not None
    assert len(result) == 2
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM etf_nav_history WHERE code='sh510300' ORDER BY date"
        ).fetchall()
    assert len(rows) == 2
    last = dict(rows[-1])
    assert last["nav"] == 3.9188
    assert last["nav_change_pct"] == 0.45
    assert last["acc_nav"] == 1.462


async def test_etf_holders_e2e(westock_service: CollectionService) -> None:
    """ETF 持有人结构：单条 + holder_account 整数。"""
    result = await westock_service.collect_etf_holders("sh510300")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM etf_holders WHERE code='sh510300'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["report_date"] == "2026-03-31"
    assert row["holder_account"] == 250000
    assert row["individual_holder_ratio"] == 65.5
    assert row["top10_ratio"] == 26.3


async def test_etf_financial_e2e(westock_service: CollectionService) -> None:
    """ETF 资产配置：5 个 ratio 列各自断言（防 stock_ratio↔bond_ratio 互换 bug）。

    不能只断"5 个 ratio 之和 ≈ 100"——若 normalizer 把 stock_ratio 写到 bond_ratio
    列（反之亦然），总和仍 ≈ 100 但语义错误。必须逐一断各列值。
    """
    result = await westock_service.collect_etf_financial("sh510300")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM etf_financial WHERE code='sh510300'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    # 5 个 ratio 各自断值（防互换错位）
    assert row["stock_ratio"] == 92.5
    assert row["bond_ratio"] == 4.5
    assert row["commodity_ratio"] == 0.0
    assert row["fund_ratio"] == 1.5
    assert row["key_asset_ratio"] == 1.5
    assert row["total_assets"] == 1_200_000_000_000.0


async def test_chip_distribution_e2e(westock_service: CollectionService) -> None:
    """筹码成本：单条 + concentration 双字段。"""
    result = await westock_service.collect_chip_distribution("sh600519")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM chip_distribution WHERE symbol='sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["close_price"] == 1800.0
    assert row["chip_profit_rate"] == 85.5
    assert row["chip_concentration_90"] == 35.2
    assert row["chip_concentration_70"] == 22.1


async def test_margintrade_e2e(westock_service: CollectionService) -> None:
    """融资融券：14 字段全落 + finance_value_dod 验证。"""
    result = await westock_service.collect_margintrade("sh600519")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM margintrade_data WHERE symbol='sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["finance_value"] == 5_000_000_000.0
    assert row["security_value"] == 80_000_000.0
    assert row["finance_value_dod"] == 15_000_000.0
    assert row["security_value_dod"] == 200_000.0


async def test_blocktrade_e2e(westock_service: CollectionService) -> None:
    """大宗交易：buy_department/sell_department 是 JSON 字符串 + 列归属正确。

    关键：必须断言 buy 字符串不出现在 sell 列，sell 字符串不出现在 buy 列——
    防止 normalizer 把 buy_department 错位写入 sell_department 列（反之亦然）。
    """
    result = await westock_service.collect_blocktrade("sh600519", "2026-06-10")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM blocktrade_data WHERE symbol='sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["date"] == "2026-06-10"
    assert row["turnover_value"] == 35_000_000.0
    assert row["close_discount_rate"] == -1.11
    # JSON 字符串可还原 + 列归属正确
    buy = json.loads(row["buy_department"])
    sell = json.loads(row["sell_department"])
    # buy 列只含 buy 营业部（防 normalizer 错位把 buy 写到 sell 列）
    assert "机构专用席位" in buy
    assert "中信证券上海分公司" in buy
    # sell 列只含 sell 营业部
    assert "华泰证券深圳益田路" in sell
    # 交叉验证：buy 字符串不出现在 sell，sell 字符串不出现在 buy
    assert "华泰证券深圳益田路" not in buy
    assert "机构专用席位" not in sell
    assert "中信证券上海分公司" not in sell


async def test_lhb_e2e(westock_service: CollectionService) -> None:
    """龙虎榜：net_buy_amount + reason + buy/sell 列归属正确。"""
    result = await westock_service.collect_lhb("sh600519", "2026-06-10")
    assert result is not None
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM lhb_data WHERE symbol='sh600519'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["name"] == "贵州茅台"
    assert row["net_buy_amount"] == 250_000_000.0
    assert row["reason"] == "涨幅偏离值达7%的证券"
    buy = json.loads(row["buy_department"])
    sell = json.loads(row["sell_department"])
    # buy 列正确
    assert "东方证券绍兴解放南路" in buy
    assert "华鑫证券上海分公司" in buy
    # sell 列正确
    assert "机构专用席位" in sell
    # 交叉验证：列归属防错位
    assert "机构专用席位" not in buy
    assert "东方证券绍兴解放南路" not in sell
    assert "华鑫证券上海分公司" not in sell


async def test_ipo_calendar_e2e(westock_service: CollectionService) -> None:
    """IPO 日历：event_type='ipo' + 关键字段。"""
    result = await westock_service.collect_ipo_calendar("hk")
    assert result is not None
    assert len(result) == 1
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ipo_exdiv_calendar WHERE event_type='ipo'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["symbol"] == "hk00999"
    assert row["market"] == "hk"
    assert row["stage"] == "申购"
    assert row["price"] == 10.5
    assert row["currency"] == "HKD"


async def test_exdiv_calendar_e2e(westock_service: CollectionService) -> None:
    """除权日历：event_type='exdiv' + dividend_per_share + dividend_plan。"""
    result = await westock_service.collect_exdiv_calendar("hk00700")
    assert result is not None
    assert len(result) == 1
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ipo_exdiv_calendar WHERE event_type='exdiv'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["ex_div_date"] == "2026-06-20"
    assert row["dividend_per_share"] == 3.4
    assert row["currency"] == "HKD"
    assert row["dividend_plan"] == "末期息"


async def test_us_finance_e2e(westock_service: CollectionService) -> None:
    """港美财务：3 个 ftype 共享同一 end_date，验证真实 UNIQUE 去重行为。

    westock CLI `finance usAAPL --type {income|balance|cashflow}` 返回的 3 个
    报表都是同一报告期（end_date 相同）。UNIQUE(symbol, end_date, period_type, source)
    让 2/3 被 INSERT OR IGNORE 跳过；本测试断言这一去重行为。
    """
    result = await westock_service.collect_us_finance("usAAPL", num=1)
    assert result is not None
    # 3 个 ftype 各自 1 行（provider 层），合并后 list 长度 = 3
    assert len(result) == 3
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM us_financials WHERE symbol='usAAPL'"
        ).fetchall()
    # 真实去重后只有 1 行（end_date 相同 + period_type 相同 + source 相同）
    assert len(rows) == 1
    row = dict(rows[0])
    # period_type 必须显式断（防 row tuple 把 period_type 错位到 period_mark 列）
    # SQL 列顺序：period_type (3), currency (4), period_mark (5), ...
    assert row["period_type"] == "annual"
    assert row["period_mark"] == "2024FY"
    assert row["currency"] == "USD"
    assert row["end_date"] == "2024-12-31"
    # raw_json 是合法 JSON（row tuple 用 json.dumps(item) 二次序列化）
    parsed = json.loads(row["raw_json"])
    assert isinstance(parsed, dict)


async def test_sector_board_e2e(westock_service: CollectionService) -> None:
    """板块首页：3 类 sector_type 共存（验证 UNIQUE(name, date, sector_type, source)）。"""
    result = await westock_service.collect_sector_board()
    assert result is not None
    assert len(result) == 3
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sector_daily_quote WHERE date='2026-06-10'"
        ).fetchall()
    assert len(rows) == 3
    by_type = {dict(r)["sector_type"]: dict(r) for r in rows}
    assert set(by_type.keys()) == {"industry", "concept", "fund_flow"}
    industry_row = by_type["industry"]
    assert industry_row["name"] == "白酒"
    assert industry_row["change_pct"] == 2.5
    assert industry_row["lead_stock"] == "贵州茅台"
    assert industry_row["main_net_inflow"] == 1_500_000_000.0


async def test_sector_hot_e2e(westock_service: CollectionService) -> None:
    """热门板块：rank + zxj + symbol 落库。"""
    result = await westock_service.collect_sector_hot(limit=10)
    assert result is not None
    assert len(result) == 1
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sector_daily_quote WHERE name='锂电池'"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["sector_type"] == "industry"
    assert row["symbol"] == "BK0670"
    assert row["rank"] == 1
    assert row["zxj"] == 1500.5


# ------------------------------------------------------------------
# 边界场景
# ------------------------------------------------------------------


async def test_unique_constraint_dedup(westock_service: CollectionService) -> None:
    """UNIQUE 去重：业务表去重 vs raw_data 审计各算各的。

    业务表 chip_distribution UNIQUE(symbol, date, source) 约束让重复采集的
    第 2 次 INSERT 被 IGNORE 跳过 → 业务表 1 行。
    raw_data 表独立于 UNIQUE（每次采集落 1 行 raw），重复采集产生 2 行 raw 审计。
    """
    # 第一次：写入
    r1 = await westock_service.collect_chip_distribution("sh600519")
    assert r1 is not None
    # 第二次：相同日期+标的 → INSERT OR IGNORE 跳过
    r2 = await westock_service.collect_chip_distribution("sh600519")
    assert r2 is not None
    with get_db() as conn:
        biz_rows = conn.execute(
            "SELECT * FROM chip_distribution WHERE symbol='sh600519'"
        ).fetchall()
        raw_rows = conn.execute(
            "SELECT * FROM raw_data WHERE data_type='chip_distribution'"
        ).fetchall()
    # 业务表去重 → 1 行
    assert len(biz_rows) == 1
    # raw_data 独立落库 → 2 行（每次采集 1 行，UNIQUE 约束不适用 raw_data）
    assert len(raw_rows) == 2


async def test_raw_data_audit_trail(westock_service: CollectionService) -> None:
    """raw_data 审计：每次采集应在 raw_data 表留 1 行 raw_json（与业务表 data_type 一致）。"""
    await westock_service.collect_chip_distribution("sh600519")
    await westock_service.collect_lhb("sh600519", "2026-06-10")
    await westock_service.collect_etf_info("sh510300")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT data_type, raw_json FROM raw_data ORDER BY id"
        ).fetchall()
    assert len(rows) == 3
    data_types = [dict(r)["data_type"] for r in rows]
    assert data_types == ["chip_distribution", "lhb", "etf_basic"]
    # 每行 raw_json 必须是合法 JSON
    for row in rows:
        parsed = json.loads(dict(row)["raw_json"])
        assert isinstance(parsed, dict)


async def test_none_field_tolerance(westock_service: CollectionService) -> None:
    """None 字段容错：mock 返回 None 字段应写 NULL 而非报错。

    us_finance 的 income 表里 total_assets 等都是 None → 应写 NULL。
    """
    await westock_service.collect_us_finance("usAAPL", num=1)
    with get_db() as conn:
        row = conn.execute(
            "SELECT total_assets, total_liabilities FROM us_financials "
            "WHERE symbol='usAAPL' AND revenue IS NOT NULL"
        ).fetchone()
    assert row is not None
    d = dict(row)
    assert d["total_assets"] is None
    assert d["total_liabilities"] is None


# ------------------------------------------------------------------
# 边界场景：provider 返回空数据 / 抛异常时的安全网
# ------------------------------------------------------------------


class _NoneReturningMockProvider(_WestockExtendedMockProvider):
    """provider 返回空数据 → collect_* 走 abort_on_invalid 路径返回 None。"""

    async def chip_distribution(self, symbol: str) -> dict | None:
        return None  # chip_distribution validate_fn: bool(data) and bool(data.get("date"))

    async def lhb(self, symbol: str, date: str) -> dict | None:
        # 返回空 dict → 默认 bool(data)==False → abort
        return {}

    async def ipo_calendar(self, market: str) -> list[dict]:
        # 返回空列表 → 默认 bool([])==False → abort
        return []


@pytest.fixture
def none_service() -> CollectionService:
    return CollectionService(
        providers={
            "structured": [_NoneReturningMockProvider()],
            "news": [],
        }
    )


async def test_abort_on_invalid_none_path(none_service: CollectionService) -> None:
    """abort_on_invalid 路径：provider 返回 None / 空 dict / 缺 date → 不落库。

    collect_chip_distribution / collect_lhb / collect_ipo_calendar 全部
    abort_on_invalid=True，验证数据无效时立即 return None，不写业务表、
    不写 raw_data。防止"空数据落入 DB"的安全网。
    """
    r_chip = await none_service.collect_chip_distribution("sh600519")
    r_lhb = await none_service.collect_lhb("sh600519", "2026-06-10")
    r_ipo = await none_service.collect_ipo_calendar("hk")
    assert r_chip is None
    assert r_lhb is None
    assert r_ipo is None
    with get_db() as conn:
        biz_count = conn.execute(
            "SELECT COUNT(*) FROM chip_distribution WHERE symbol='sh600519'"
        ).fetchone()[0]
        lhb_count = conn.execute(
            "SELECT COUNT(*) FROM lhb_data WHERE symbol='sh600519'"
        ).fetchone()[0]
        ipo_count = conn.execute(
            "SELECT COUNT(*) FROM ipo_exdiv_calendar"
        ).fetchone()[0]
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM raw_data"
        ).fetchone()[0]
    # 业务表全空 + raw_data 也不落库
    assert biz_count == 0
    assert lhb_count == 0
    assert ipo_count == 0
    assert raw_count == 0


class _RaisingMockProvider(_WestockExtendedMockProvider):
    """provider 抛异常 → collect_* 的 _template.py try/except 捕获后 return None。"""

    async def chip_distribution(self, symbol: str) -> dict | None:
        raise RuntimeError("westock CLI 模拟崩溃")

    async def lhb(self, symbol: str, date: str) -> dict | None:
        raise ValueError("lhb upstream error")


@pytest.fixture
def raising_service() -> CollectionService:
    return CollectionService(
        providers={
            "structured": [_RaisingMockProvider()],
            "news": [],
        }
    )


async def test_provider_exception_swallowed(raising_service: CollectionService) -> None:
    """异常吞噬：provider 抛 RuntimeError / ValueError → collect_* 捕获并返回 None。

    验证 _template.py L78-86 的 try/except 行为：单次 provider 抛错不冒泡到 caller，
    不写业务表、不写 raw_data，循环继续（无其他 provider 可尝试时整体 return None）。
    防止单个数据源崩溃阻塞整个 collect_* 流程。
    """
    r_chip = await raising_service.collect_chip_distribution("sh600519")
    r_lhb = await raising_service.collect_lhb("sh600519", "2026-06-10")
    assert r_chip is None
    assert r_lhb is None
    with get_db() as conn:
        biz_count = conn.execute(
            "SELECT COUNT(*) FROM chip_distribution"
        ).fetchone()[0]
        lhb_count = conn.execute(
            "SELECT COUNT(*) FROM lhb_data"
        ).fetchone()[0]
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM raw_data"
        ).fetchone()[0]
    assert biz_count == 0
    assert lhb_count == 0
    assert raw_count == 0
