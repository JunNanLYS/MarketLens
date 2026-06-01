import tempfile
from pathlib import Path

import pytest

from backend.storage.database import set_db_path
from backend.storage.schema import init_db
from backend.storage.repository import (
    delete,
    execute_modify,
    execute_query,
    get_by_id,
    insert,
    list_paginated,
    update,
)


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path: str = f.name
    set_db_path(path)
    init_db()
    yield
    set_db_path(None)
    Path(path).unlink(missing_ok=True)


def test_insert_and_get_by_id() -> None:
    data: dict = {"symbol": "sh600000", "name": "浦发银行", "market": "sh"}
    row_id: int = insert("tracked_assets", data)
    assert isinstance(row_id, int)
    assert row_id > 0
    row: dict | None = get_by_id("tracked_assets", row_id)
    assert row is not None
    assert row["symbol"] == "sh600000"
    assert row["name"] == "浦发银行"
    assert row["market"] == "sh"


def test_get_by_id_not_found() -> None:
    row: dict | None = get_by_id("tracked_assets", 999)
    assert row is None


def test_list_paginated_basic() -> None:
    for i in range(25):
        insert(
            "tracked_assets",
            {"symbol": f"sh6000{i:02d}", "name": f"股票{i}", "market": "sh"},
        )
    result: dict = list_paginated("tracked_assets", page=1, page_size=10)
    assert len(result["items"]) == 10
    assert result["page_info"]["total"] == 25
    assert result["page_info"]["total_pages"] == 3
    assert result["page_info"]["page"] == 1


def test_list_paginated_last_page() -> None:
    for i in range(25):
        insert(
            "tracked_assets",
            {"symbol": f"sh6000{i:02d}", "name": f"股票{i}", "market": "sh"},
        )
    result: dict = list_paginated("tracked_assets", page=3, page_size=10)
    assert len(result["items"]) == 5
    assert result["page_info"]["page"] == 3


def test_list_paginated_with_filters() -> None:
    insert("tracked_assets", {"symbol": "sh600000", "name": "浦发银行", "market": "sh"})
    insert("tracked_assets", {"symbol": "sz000001", "name": "平安银行", "market": "sz"})
    result: dict = list_paginated("tracked_assets", filters={"market": "sh"})
    assert len(result["items"]) == 1
    assert result["items"][0]["market"] == "sh"


def test_list_paginated_with_order_by() -> None:
    insert("tracked_assets", {"symbol": "sh600000", "name": "B股票", "market": "sh"})
    insert("tracked_assets", {"symbol": "sh600001", "name": "A股票", "market": "sh"})
    result: dict = list_paginated("tracked_assets", order_by="name")
    assert result["items"][0]["name"] == "A股票"


def test_list_paginated_empty() -> None:
    result: dict = list_paginated("tracked_assets", page=1, page_size=10)
    assert len(result["items"]) == 0
    assert result["page_info"]["total"] == 0
    assert result["page_info"]["total_pages"] == 0


def test_update() -> None:
    row_id: int = insert(
        "tracked_assets", {"symbol": "sh600000", "name": "浦发银行", "market": "sh"}
    )
    success: bool = update("tracked_assets", row_id, {"name": "新名称"})
    assert success is True
    row: dict | None = get_by_id("tracked_assets", row_id)
    assert row is not None
    assert row["name"] == "新名称"


def test_update_not_found() -> None:
    success: bool = update("tracked_assets", 999, {"name": "新名称"})
    assert success is False


def test_delete_hard() -> None:
    row_id: int = insert(
        "tracked_assets", {"symbol": "sh600000", "name": "浦发银行", "market": "sh"}
    )
    success: bool = delete("tracked_assets", row_id)
    assert success is True
    row: dict | None = get_by_id("tracked_assets", row_id)
    assert row is None


def test_delete_soft() -> None:
    row_id: int = insert("accounts", {"name": "测试账户", "currency": "CNY"})
    success: bool = delete("accounts", row_id, soft=True)
    assert success is True
    row: dict | None = get_by_id("accounts", row_id)
    assert row is not None
    assert row["deleted_at"] is not None


def test_delete_not_found() -> None:
    success: bool = delete("tracked_assets", 999)
    assert success is False


def test_execute_query() -> None:
    insert("tracked_assets", {"symbol": "sh600000", "name": "浦发银行", "market": "sh"})
    results: list[dict] = execute_query(
        "SELECT * FROM tracked_assets WHERE symbol = ?", ("sh600000",)
    )
    assert len(results) == 1
    assert results[0]["symbol"] == "sh600000"


def test_execute_modify() -> None:
    row_id: int = insert(
        "tracked_assets", {"symbol": "sh600000", "name": "浦发银行", "market": "sh"}
    )
    affected: int = execute_modify(
        "UPDATE tracked_assets SET name = ? WHERE id = ?", ("新名称", row_id)
    )
    assert affected == 1
