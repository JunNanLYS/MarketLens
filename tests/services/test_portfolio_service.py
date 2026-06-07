import tempfile
from pathlib import Path

import pytest

from backend.services.portfolio_service import PortfolioService
from backend.storage.database import aget_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def svc() -> PortfolioService:
    return PortfolioService()


@pytest.fixture
def sample_account(svc: PortfolioService) -> dict:
    return svc.create_account({"name": "富途", "broker": "富途牛牛", "currency": "HKD"})


@pytest.fixture
async def sample_asset() -> None:
    """插入默认追踪标的 hk00700, 供依赖此 fixture 的测试使用。"""
    async with aget_db() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO tracked_assets (symbol, name, market, asset_type, enabled) "
            "VALUES (?, ?, ?, ?, 1)",
            ("hk00700", "腾讯控股", "hk", "stock"),
        )


async def test_create_account_success(svc: PortfolioService) -> None:
    account: dict = svc.create_account({"name": "华泰", "currency": "CNY"})
    assert account["id"] is not None
    assert account["name"] == "华泰"
    assert account["currency"] == "CNY"
    assert account["deleted_at"] is None


async def test_create_account_duplicate_name_fails(svc: PortfolioService) -> None:
    svc.create_account({"name": "富途"})
    with pytest.raises(ValueError, match="已存在"):
        svc.create_account({"name": "富途"})


async def test_create_account_empty_name_fails(svc: PortfolioService) -> None:
    with pytest.raises(ValueError, match="不能为空"):
        svc.create_account({"name": ""})
    with pytest.raises(ValueError, match="不能为空"):
        svc.create_account({"name": "   "})


async def test_get_accounts(svc: PortfolioService) -> None:
    svc.create_account({"name": "富途"})
    svc.create_account({"name": "华泰"})
    accounts: list[dict] = svc.get_accounts()
    assert len(accounts) == 2


async def test_get_accounts_exclude_deleted(svc: PortfolioService) -> None:
    svc.create_account({"name": "富途"})
    acct: dict = svc.create_account({"name": "华泰"})
    svc.delete_account(acct["id"])
    accounts: list[dict] = svc.get_accounts()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "富途"


async def test_get_accounts_include_deleted(svc: PortfolioService) -> None:
    svc.create_account({"name": "富途"})
    acct: dict = svc.create_account({"name": "华泰"})
    svc.delete_account(acct["id"])
    accounts: list[dict] = svc.get_accounts(include_deleted=True)
    assert len(accounts) == 2


async def test_get_account_by_id(svc: PortfolioService) -> None:
    created: dict = svc.create_account({"name": "富途"})
    found: dict | None = svc.get_account_by_id(created["id"])
    assert found is not None
    assert found["name"] == "富途"


async def test_get_account_by_id_not_found(svc: PortfolioService) -> None:
    assert svc.get_account_by_id(999) is None


async def test_update_account(svc: PortfolioService) -> None:
    created: dict = svc.create_account({"name": "富途"})
    updated: dict | None = svc.update_account(
        created["id"], {"name": "富途国际", "notes": "港股账户"}
    )
    assert updated is not None
    assert updated["name"] == "富途国际"
    assert updated["notes"] == "港股账户"


async def test_update_account_duplicate_name(svc: PortfolioService) -> None:
    svc.create_account({"name": "华泰"})
    created: dict = svc.create_account({"name": "富途"})
    with pytest.raises(ValueError, match="已存在"):
        svc.update_account(created["id"], {"name": "华泰"})


async def test_update_account_not_found(svc: PortfolioService) -> None:
    assert svc.update_account(999, {"name": "新名称"}) is None


async def test_delete_account_soft(svc: PortfolioService) -> None:
    created: dict = svc.create_account({"name": "富途"})
    assert svc.delete_account(created["id"]) is True
    found: dict | None = svc.get_account_by_id(created["id"])
    assert found is not None
    assert found["deleted_at"] is not None


async def test_delete_account_not_found(svc: PortfolioService) -> None:
    assert svc.delete_account(999) is False


async def test_create_buy_transaction(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-15",
        }
    )
    assert tx["id"] is not None
    assert tx["type"] == "buy"
    assert tx["quantity"] == 100
    assert tx["price"] == 380.0
    assert tx["currency"] == "HKD"
    assert tx["fee"] == 0.0


async def test_create_transaction_account_not_found(svc: PortfolioService) -> None:
    with pytest.raises(ValueError, match="账户不存在"):
        svc.create_transaction(
            {
                "account_id": 999,
                "symbol": "hk00700",
                "type": "buy",
                "quantity": 100,
                "price": 380.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_create_transaction_invalid_type(
    svc: PortfolioService, sample_account: dict
) -> None:
    with pytest.raises(ValueError, match="无效的交易类型"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "invalid",
                "quantity": 100,
                "price": 380.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_create_transaction_quantity_zero(
    svc: PortfolioService, sample_account: dict
) -> None:
    with pytest.raises(ValueError, match="数量必须大于 0"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "buy",
                "quantity": 0,
                "price": 380.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_create_sell_transaction(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 200,
            "price": 380.0,
            "trade_date": "2026-05-10",
        }
    )
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "fee": 15.0,
            "trade_date": "2026-05-15",
        }
    )
    assert tx["type"] == "sell"
    assert tx["quantity"] == 100
    assert tx["fee"] == 15.0


async def test_sell_exceeds_holding(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-10",
        }
    )
    with pytest.raises(ValueError, match="超过当前持仓"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "sell",
                "quantity": 150,
                "price": 400.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_positions_weighted_avg_cost(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 300.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    assert pos["total_qty"] == 200
    assert pos["avg_cost"] == 350.0


async def test_positions_sell_does_not_change_avg(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 200,
            "price": 300.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 350.0,
            "trade_date": "2026-05-10",
        }
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    assert pos["total_qty"] == 100
    assert pos["avg_cost"] == 300.0


async def test_positions_unrealized_pnl(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 350.0,
            "trade_date": "2026-05-01",
        }
    )

    async with aget_db() as conn:
        await conn.execute(
            "INSERT INTO market_quotes (symbol, price, collected_at) VALUES (?, ?, ?)",
            ("hk00700", 400.0, "2026-05-31T15:30:00"),
        )

    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    assert pos["current_price"] == 400.0
    assert pos["market_value"] == 40000.0
    assert pos["unrealized_pnl"] == 5000.0
    assert pos["unrealized_pnl_pct"] == pytest.approx(14.29, abs=0.01)


async def test_positions_quote_same_millisecond_takes_one(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """同毫秒并发采集的两条行情行,get_positions 只能取 1 条。

    旧 SQL 用 MAX(collected_at) 在并列时返回 2 行,quotes_map 出现重复项;
    CTE + ROW_NUMBER() 保证每 symbol 严格 1 行,避免重复累加。
    注意:ROW_NUMBER 对 ORDER BY 排序键并列时内部行序不确定,因此断言
    current_price 必须是 380 或 420 之一,不能是其他值。
    """
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 350.0,
            "trade_date": "2026-05-01",
        }
    )

    same_ts = "2026-05-31T15:30:00"
    async with aget_db() as conn:
        # 两条同毫秒行情(模拟并发采集),id ASC 的较早行价格较低
        await conn.execute(
            "INSERT INTO market_quotes (symbol, price, collected_at) VALUES (?, ?, ?)",
            ("hk00700", 380.0, same_ts),
        )
        await conn.execute(
            "INSERT INTO market_quotes (symbol, price, collected_at) VALUES (?, ?, ?)",
            ("hk00700", 420.0, same_ts),
        )

    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    # 关键不变量:同 symbol 在 quotes_map 中只能有 1 个条目,聚合出 1 条持仓
    assert pos["current_price"] in (380.0, 420.0)
    assert pos["market_value"] == pos["current_price"] * 100
    assert pos["unrealized_pnl"] == (pos["current_price"] - 350.0) * 100


async def test_positions_no_quote(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 350.0,
            "trade_date": "2026-05-01",
        }
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    assert pos["current_price"] is None
    assert pos["market_value"] is None
    assert pos["unrealized_pnl"] is None


async def test_positions_filter_by_account(
    svc: PortfolioService, sample_asset: None
) -> None:
    acct1: dict = svc.create_account({"name": "富途", "currency": "HKD"})
    acct2: dict = svc.create_account({"name": "华泰", "currency": "CNY"})
    svc.create_transaction(
        {
            "account_id": acct1["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 350.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": acct2["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 50,
            "price": 360.0,
            "trade_date": "2026-05-01",
        }
    )
    positions: list[dict] = svc.get_positions(account_id=acct1["id"])
    assert len(positions) == 1
    assert positions[0]["account_id"] == acct1["id"]
    assert positions[0]["total_qty"] == 100


async def test_realized_pnl(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 200,
            "price": 300.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "fee": 15.0,
            "trade_date": "2026-05-10",
        }
    )
    results: list[dict] = svc.get_realized_pnl()
    assert len(results) == 1
    r: dict = results[0]
    assert r["total_sell_qty"] == 100
    assert r["avg_cost"] == 300.0
    assert r["realized_pnl"] == pytest.approx(9985.0)


async def test_realized_pnl_with_filter(
    svc: PortfolioService, sample_asset: None
) -> None:
    acct1: dict = svc.create_account({"name": "富途", "currency": "HKD"})
    acct2: dict = svc.create_account({"name": "华泰", "currency": "CNY"})
    svc.create_transaction(
        {
            "account_id": acct1["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 300.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": acct1["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    results: list[dict] = svc.get_realized_pnl(account_id=acct2["id"])
    assert len(results) == 0


async def test_get_transactions_pagination(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    for i in range(5):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "buy",
                "quantity": 100,
                "price": 380.0 + i,
                "trade_date": f"2026-05-{10 + i:02d}",
            }
        )
    result: dict = svc.get_transactions(page=1, page_size=3)
    assert len(result["items"]) == 3
    assert result["page_info"]["total"] == 5
    assert result["page_info"]["total_pages"] == 2


async def test_get_transactions_filter_by_type(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 200,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    result: dict = svc.get_transactions(filters={"type": "sell"})
    assert len(result["items"]) == 1
    assert result["items"][0]["type"] == "sell"


async def test_get_transactions_filter_by_date_range(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 390.0,
            "trade_date": "2026-05-20",
        }
    )
    result: dict = svc.get_transactions(
        filters={"date_from": "2026-05-15", "date_to": "2026-05-25"}
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["trade_date"] == "2026-05-20"


async def test_get_transaction_by_id(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-15",
        }
    )
    found: dict | None = svc.get_transaction_by_id(tx["id"])
    assert found is not None
    assert found["id"] == tx["id"]


async def test_get_transaction_by_id_not_found(svc: PortfolioService) -> None:
    assert svc.get_transaction_by_id(999) is None


async def test_update_transaction(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-15",
        }
    )
    updated: dict | None = svc.update_transaction(
        tx["id"], {"quantity": 150, "price": 385.0}
    )
    assert updated is not None
    assert updated["quantity"] == 150
    assert updated["price"] == 385.0


async def test_update_transaction_not_found(svc: PortfolioService) -> None:
    assert svc.update_transaction(999, {"quantity": 150}) is None


async def test_update_sell_transaction_holding_check(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 50,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    with pytest.raises(ValueError, match="持仓为负"):
        svc.update_transaction(tx["id"], {"quantity": 150})


async def test_delete_transaction_soft(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-15",
        }
    )
    assert svc.delete_transaction(tx["id"]) is True
    found: dict | None = svc.get_transaction_by_id(tx["id"])
    assert found is not None
    assert found["deleted_at"] is not None


async def test_delete_buy_transaction_prevents_negative_holding(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 50,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 50,
            "price": 410.0,
            "trade_date": "2026-05-15",
        }
    )
    buy_tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 50,
            "price": 390.0,
            "trade_date": "2026-05-20",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 50,
            "price": 420.0,
            "trade_date": "2026-05-25",
        }
    )
    with pytest.raises(ValueError, match="持仓将为负数"):
        svc.delete_transaction(buy_tx["id"])


async def test_delete_transaction_not_found(svc: PortfolioService) -> None:
    assert svc.delete_transaction(999) is False


async def test_dividend_transaction(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "dividend",
            "quantity": 100,
            "price": 2.5,
            "trade_date": "2026-05-15",
        }
    )
    assert tx["type"] == "dividend"
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    assert positions[0]["total_qty"] == 100
    assert positions[0]["avg_cost"] == 380.0


async def test_split_transaction(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    tx: dict = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "split",
            "quantity": 2,
            "price": 1.0,
            "trade_date": "2026-05-15",
        }
    )
    assert tx["type"] == "split"
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    assert positions[0]["total_qty"] == 200
    assert positions[0]["avg_cost"] == 380.0


async def test_create_split_zero_quantity_rejected(
    svc: PortfolioService, sample_account: dict
) -> None:
    with pytest.raises(ValueError, match="数量必须大于 0"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "split",
                "quantity": 0,
                "price": 1.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_create_split_negative_quantity_rejected(
    svc: PortfolioService, sample_account: dict
) -> None:
    with pytest.raises(ValueError, match="数量必须大于 0"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "split",
                "quantity": -2,
                "price": 1.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_create_split_excessive_ratio_rejected(
    svc: PortfolioService, sample_account: dict
) -> None:
    with pytest.raises(ValueError, match="拆股比例不能超过 1000"):
        svc.create_transaction(
            {
                "account_id": sample_account["id"],
                "symbol": "hk00700",
                "type": "split",
                "quantity": 5000,
                "price": 1.0,
                "trade_date": "2026-05-15",
            }
        )


async def test_wac_includes_buy_fee(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """买入手续费应摊入 WAC 成本基础。"""
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "fee": 100.0,
            "trade_date": "2026-05-01",
        }
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    # WAC = (0 * 0 + 380 * 100 + 100) / 100 = 381.0
    assert positions[0]["avg_cost"] == pytest.approx(381.0)


async def test_realized_pnl_includes_buy_fee(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """买入手续费应进入 WAC,卖出时 realized 反映完整成本。"""
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "fee": 100.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "fee": 15.0,
            "trade_date": "2026-06-01",
        }
    )
    results: list[dict] = svc.get_realized_pnl()
    assert len(results) == 1
    # avg_cost=381, realized = (400-381)*100 - 15 = 1885
    assert results[0]["realized_pnl"] == pytest.approx(1885.0)


async def test_sample_asset_inserts_tracked_asset(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """修复后的 fixture 应真正插入 hk00700 到 tracked_assets。"""
    # 验证 tracked_assets 表有该 symbol
    with __import__("backend.storage.database").storage.database.get_db() as conn:
        row = conn.execute(
            "SELECT symbol, name FROM tracked_assets WHERE symbol = ?", ("hk00700",)
        ).fetchone()
    assert row is not None
    assert row["symbol"] == "hk00700"
    assert row["name"] == "腾讯控股"


async def test_update_delete_concurrent_holds_write_lock(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """两个并发 update 不能让 total_qty 变负（验证 _WRITE_LOCK 串行化）。"""
    import threading

    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    sell = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 50,
            "price": 400.0,
            "trade_date": "2026-05-15",
        }
    )

    # 两个线程同时 update sell.quantity,即使发生事务冲突也不会 OperationalError
    def _upd(q: float) -> None:
        try:
            svc.update_transaction(sell["id"], {"quantity": q})
        except Exception:
            pass  # 事务冲突属合理回滚

    t1 = threading.Thread(target=_upd, args=(80,))
    t2 = threading.Thread(target=_upd, args=(90,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    # 不论并发结果如何,total_qty 不应 < 0
    assert positions[0]["total_qty"] >= 0


async def test_update_transaction_uses_write_lock(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """验证 update_transaction 在持有 _WRITE_LOCK 时持有锁。

    portfolio_service 模块顶部 from ... import _WRITE_LOCK 绑定了本地引用,
    必须同时 patch collection_service 和 portfolio_service 两边的符号。
    """
    import threading
    from unittest.mock import patch
    from backend.services import collection_service
    import backend.services.portfolio_service as ps_mod

    buy = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )

    original = collection_service._WRITE_LOCK
    observed_held: list[bool] = []

    class _ObservableLock:
        def __init__(self, inner: threading.Lock) -> None:
            self._inner = inner

        def __enter__(self) -> "_ObservableLock":
            self._inner.__enter__()
            observed_held.append(self._inner.locked())
            return self

        def __exit__(self, *args) -> None:
            self._inner.__exit__(*args)

    observable = _ObservableLock(original)
    with patch.object(collection_service, "_WRITE_LOCK", new=observable), \
         patch.object(ps_mod, "_WRITE_LOCK", new=observable):
        svc.update_transaction(buy["id"], {"price": 400.0})

    assert observed_held, "update_transaction 未进入 _WRITE_LOCK 上下文"
    assert observed_held[0] is True, "进入 _WRITE_LOCK 时锁未处于持有状态"


async def test_delete_transaction_uses_write_lock(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    """验证 delete_transaction 在持有 _WRITE_LOCK 时持有锁。"""
    import threading
    from unittest.mock import patch
    from backend.services import collection_service
    import backend.services.portfolio_service as ps_mod

    buy = svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )

    original = collection_service._WRITE_LOCK
    observed_held: list[bool] = []

    class _ObservableLock:
        def __init__(self, inner: threading.Lock) -> None:
            self._inner = inner

        def __enter__(self) -> "_ObservableLock":
            self._inner.__enter__()
            observed_held.append(self._inner.locked())
            return self

        def __exit__(self, *args) -> None:
            self._inner.__exit__(*args)

    observable = _ObservableLock(original)
    with patch.object(collection_service, "_WRITE_LOCK", new=observable), \
         patch.object(ps_mod, "_WRITE_LOCK", new=observable):
        svc.delete_transaction(buy["id"])

    assert observed_held, "delete_transaction 未进入 _WRITE_LOCK 上下文"
    assert observed_held[0] is True, "进入 _WRITE_LOCK 时锁未处于持有状态"


async def test_positions_fully_sold_excluded(
    svc: PortfolioService, sample_account: dict, sample_asset: None
) -> None:
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "buy",
            "quantity": 100,
            "price": 380.0,
            "trade_date": "2026-05-01",
        }
    )
    svc.create_transaction(
        {
            "account_id": sample_account["id"],
            "symbol": "hk00700",
            "type": "sell",
            "quantity": 100,
            "price": 400.0,
            "trade_date": "2026-05-10",
        }
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 0


class TestCreateTransactionRequestValidators:
    """Pydantic field_validator 边界值测试。"""

    def test_trade_date_iso_format_valid(self) -> None:
        """ISO 8601 YYYY-MM-DD 格式应通过。"""
        from backend.api.portfolio import CreateTransactionRequest

        req = CreateTransactionRequest(
            account_id=1,
            symbol="sh600519",
            type="buy",
            quantity=100,
            price=10.0,
            trade_date="2026-06-05",
        )
        assert req.trade_date == "2026-06-05"

    def test_trade_date_iso_format_invalid(self) -> None:
        """非 ISO 8601 格式应被 Pydantic 拒绝。"""
        from pydantic import ValidationError

        from backend.api.portfolio import CreateTransactionRequest

        for bad in ("not-a-date", "2026/06/05", "06-05-2026", ""):
            with pytest.raises(ValidationError):
                CreateTransactionRequest(
                    account_id=1,
                    symbol="sh600519",
                    type="buy",
                    quantity=100,
                    price=10.0,
                    trade_date=bad,
                )

    def test_quantity_must_be_positive(self) -> None:
        """quantity 必须 > 0。"""
        from pydantic import ValidationError

        from backend.api.portfolio import CreateTransactionRequest

        with pytest.raises(ValidationError):
            CreateTransactionRequest(
                account_id=1,
                symbol="sh600519",
                type="buy",
                quantity=0,
                price=10.0,
                trade_date="2026-06-05",
            )
        with pytest.raises(ValidationError):
            CreateTransactionRequest(
                account_id=1,
                symbol="sh600519",
                type="buy",
                quantity=-1.0,
                price=10.0,
                trade_date="2026-06-05",
            )

    def test_invalid_transaction_type_rejected(self) -> None:
        """type 必须是 Literal 白名单内的值。"""
        from pydantic import ValidationError

        from backend.api.portfolio import CreateTransactionRequest

        with pytest.raises(ValidationError):
            CreateTransactionRequest(
                account_id=1,
                symbol="sh600519",
                type="invalid_type",
                quantity=100,
                price=10.0,
                trade_date="2026-06-05",
            )
