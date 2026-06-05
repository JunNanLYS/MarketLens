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
    pass

async def __insert(table: str, data: dict) -> int:
    async with aget_db() as conn:
        keys = list(data.keys())
        cols = ', '.join(keys)
        placeholders = ', '.join(['?'] * len(keys))
        sql = f'INSERT INTO {table} ({cols}) VALUES ({placeholders})'
        cursor = await conn.execute(sql, list(data.values()))
        return cursor.lastrowid

    await __insert(
        "tracked_assets",
        {"symbol": "hk00700", "name": "腾讯控股", "market": "hk"},
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

async def __insert(table: str, data: dict) -> int:
    async with aget_db() as conn:
        keys = list(data.keys())
        cols = ', '.join(keys)
        placeholders = ', '.join(['?'] * len(keys))
        sql = f'INSERT INTO {table} ({cols}) VALUES ({placeholders})'
        cursor = await conn.execute(sql, list(data.values()))
        return cursor.lastrowid

    await __insert(
        "market_quotes",
        {
            "symbol": "hk00700",
            "price": 400.0,
            "collected_at": "2026-05-31T15:30:00",
        },
    )
    positions: list[dict] = svc.get_positions()
    assert len(positions) == 1
    pos: dict = positions[0]
    assert pos["current_price"] == 400.0
    assert pos["market_value"] == 40000.0
    assert pos["unrealized_pnl"] == 5000.0
    assert pos["unrealized_pnl_pct"] == pytest.approx(14.29, abs=0.01)


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
