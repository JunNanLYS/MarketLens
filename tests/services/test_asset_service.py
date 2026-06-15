import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.collectors.base import BaseProvider
from backend.services import collection_service
from backend.services.asset_service import AssetExistsError, AssetService
from backend.storage.database import aget_db, set_db_path
from backend.storage.schema import init_db_sync as init_db


class FakeProvider(BaseProvider):
    def __init__(
        self, name: str = "fake", search_results: list[dict] | None = None
    ) -> None:
        super().__init__(name=name)
        self._search_results = search_results or []

    async def search(self, keyword: str) -> list[dict]:
        return self._search_results

    async def quote(self, symbols: list[str]) -> list[dict]:
        return []

    async def kline(self, symbol: str, period: str = "daily") -> list[dict]:
        return []

    async def finance(self, symbol: str) -> dict:
        return {}

    async def fund_flow(self, symbol: str) -> dict:
        return {}

    async def technical(self, symbol: str) -> dict:
        return {}


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
def fake_providers() -> dict[str, list[BaseProvider]]:
    return {"structured": [FakeProvider(name="fake")], "news": []}


@pytest.fixture
def service(fake_providers: dict[str, list[BaseProvider]]) -> AssetService:
    return AssetService(providers=fake_providers)


def test_asset_service_uses_collection_write_lock() -> None:
    """AssetService 写路径应复用 collection_service 暴露的同一把锁。"""
    import backend.services.asset_service as asset_service_module

    assert asset_service_module._WRITE_LOCK is collection_service._WRITE_LOCK


async def test_add_asset_success(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "hk00700"})
    assert result["symbol"] == "hk00700"
    assert result["market"] == "hk"
    assert result["enabled"] is True or result["enabled"] == 1
    assert result["asset_type"] == "stock"
    assert "id" in result


async def test_add_asset_with_name_and_tags(service: AssetService) -> None:
    result = await service.add_asset(
        {
            "symbol": "sh600519",
            "name": "贵州茅台",
            "tags": ["白酒", "A股"],
            "notes": "长期持有",
        }
    )
    assert result["name"] == "贵州茅台"
    assert result["tags"] == ["白酒", "A股"]
    assert result["notes"] == "长期持有"
    assert result["market"] == "sh"


async def test_add_asset_infer_market_us(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "usAAPL"})
    assert result["market"] == "us"


async def test_add_asset_infer_market_fut(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "futrb2501"})
    assert result["market"] == "fut"


async def test_add_asset_duplicate(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700"})
    with pytest.raises(ValueError, match="已在追踪列表"):
        await service.add_asset({"symbol": "hk00700"})


async def test_add_asset_invalid_symbol(service: AssetService) -> None:
    with pytest.raises(ValueError, match="无法识别"):
        await service.add_asset({"symbol": "xyz999"})


async def test_add_asset_empty_symbol(service: AssetService) -> None:
    with pytest.raises(ValueError):
        await service.add_asset({"symbol": ""})


async def test_add_asset_auto_search_name() -> None:
    fake = FakeProvider(
        name="fake",
        search_results=[{"symbol": "hk00700", "name": "腾讯控股", "market": "hk"}],
    )
    svc = AssetService(providers={"structured": [fake], "news": []})
    result = await svc.add_asset({"symbol": "hk00700"})
    assert result["name"] == "腾讯控股"


async def test_get_assets_default_enabled_only(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    await service.add_asset({"symbol": "sh600519", "name": "贵州茅台"})
    service.delete_asset(1, soft=True)

    result = service.get_assets()
    assert len(result["items"]) == 1
    assert result["items"][0]["symbol"] == "sh600519"


async def test_get_assets_with_enabled_false(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    service.delete_asset(1, soft=True)

    result = service.get_assets(filters={"enabled": False})
    assert len(result["items"]) == 1
    assert result["items"][0]["symbol"] == "hk00700"


async def test_get_assets_pagination(service: AssetService) -> None:
    for i in range(5):
        await service.add_asset({"symbol": f"sh6000{i:02d}", "name": f"股票{i}"})

    result = service.get_assets(page=1, page_size=2)
    assert len(result["items"]) == 2
    assert result["page_info"]["total"] == 5
    assert result["page_info"]["total_pages"] == 3
    assert result["page_info"]["page"] == 1


async def test_get_assets_filter_by_market(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    await service.add_asset({"symbol": "sh600519", "name": "贵州茅台"})

    result = service.get_assets(filters={"market": "hk"})
    assert len(result["items"]) == 1
    assert result["items"][0]["market"] == "hk"


async def test_get_assets_filter_by_tag(service: AssetService) -> None:
    await service.add_asset(
        {"symbol": "hk00700", "name": "腾讯控股", "tags": ["互联网"]}
    )
    await service.add_asset(
        {"symbol": "sh600519", "name": "贵州茅台", "tags": ["白酒"]}
    )

    result = service.get_assets(filters={"tag": "互联网"})
    assert len(result["items"]) == 1
    assert result["items"][0]["symbol"] == "hk00700"


async def test_get_assets_with_quote(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        await conn.execute(
            """INSERT INTO market_quotes (symbol, price, change_pct, collected_at)
               VALUES (?, ?, ?, datetime('now'))""",
            ("hk00700", 385.0, 1.2),
        )

    result = service.get_assets()
    assert len(result["items"]) == 1
    assert result["items"][0]["latest_price"] == 385.0
    assert result["items"][0]["latest_change_pct"] == 1.2


async def test_get_asset_by_id_basic(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["symbol"] == "hk00700"
    assert result["name"] == "腾讯控股"
    assert result["quote"] is None
    assert result["kline_summary"] is None
    assert result["finance_summary"] is None
    assert result["fund_flow_summary"] is None
    assert result["latest_report"] is None


async def test_get_asset_by_id_with_quote(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        await conn.execute(
            """INSERT INTO market_quotes (symbol, price, change, change_pct, open, high, low, prev_close, volume, amount, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("hk00700", 385.0, 4.6, 1.2, 382.0, 387.5, 381.0, 380.4, 23456789, 9034567890.0),
        )

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["quote"] is not None
    assert result["quote"]["price"] == 385.0
    assert result["quote"]["prev_close"] == 380.4
    assert result["quote"]["amount"] == 9034567890.0


async def test_get_asset_by_id_with_kline(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        for i in range(60):
            await conn.execute(
                """INSERT INTO kline_daily (symbol, date, close, collected_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                ("hk00700", f"2026-05-{i + 1:02d}", 370.0 + i * 0.3),
            )

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["kline_summary"] is not None
    assert result["kline_summary"]["ma5"] is not None
    assert result["kline_summary"]["ma20"] is not None
    assert result["kline_summary"]["ma60"] is not None
    assert result["kline_summary"]["trend"] != "数据不足"


async def test_get_asset_by_id_with_finance(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        await conn.execute(
            """INSERT INTO financial_reports (symbol, report_period, revenue_yoy, eps, roe, collected_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("hk00700", "2026Q1", 8.5, 12.8, 18.2),
        )

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["finance_summary"] is not None
    assert result["finance_summary"]["report_period"] == "2026Q1"


async def test_get_asset_by_id_with_fund_flow(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        for i in range(5):
            await conn.execute(
                """INSERT INTO fund_flows (symbol, date, main_net_inflow, collected_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                ("hk00700", f"2026-05-{26 + i:02d}", 100000000.0),
            )

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["fund_flow_summary"] is not None
    assert result["fund_flow_summary"]["net_flow_5d"] == 500000000.0


async def test_get_asset_by_id_with_ai_report(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})

    async with aget_db() as conn:
        await conn.execute(
            """INSERT INTO ai_reports (symbol, action, confidence, risk_level, generated_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("hk00700", "watch", 0.52, "medium"),
        )

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["latest_report"] is not None
    assert result["latest_report"]["action"] == "watch"


async def test_get_asset_by_id_not_found(service: AssetService) -> None:
    result = service.get_asset_by_id(999)
    assert result is None


async def test_update_asset_tags(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    result = service.update_asset(asset["id"], {"tags": ["互联网", "AI概念"]})
    assert result is not None
    assert result["tags"] == ["互联网", "AI概念"]


async def test_update_asset_enabled(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    result = service.update_asset(asset["id"], {"enabled": False})
    assert result is not None
    assert result["enabled"] == 0 or result["enabled"] is False


async def test_update_asset_notes(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    result = service.update_asset(asset["id"], {"notes": "增加备注"})
    assert result is not None
    assert result["notes"] == "增加备注"


async def test_update_asset_not_found(service: AssetService) -> None:
    result = service.update_asset(999, {"notes": "test"})
    assert result is None


async def test_update_asset_empty_data(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    result = service.update_asset(asset["id"], {})
    assert result is not None
    assert result["symbol"] == "hk00700"


async def test_delete_asset_soft(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    success = service.delete_asset(asset["id"], soft=True)
    assert success is True

    result = service.get_asset_by_id(asset["id"])
    assert result is not None
    assert result["enabled"] == 0 or result["enabled"] is False


async def test_delete_asset_hard(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    success = service.delete_asset(asset["id"], soft=False)
    assert success is True

    result = service.get_asset_by_id(asset["id"])
    assert result is None


async def test_delete_asset_not_found(service: AssetService) -> None:
    success = service.delete_asset(999, soft=True)
    assert success is False


async def test_delete_asset_soft_already_disabled(service: AssetService) -> None:
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    service.delete_asset(asset["id"], soft=True)
    success = service.delete_asset(asset["id"], soft=True)
    assert success is False


async def test_add_asset_reenables_soft_deleted(service: AssetService) -> None:
    """软删除后重新添加同一 symbol → 重新启用而非报错。"""
    asset = await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    service.delete_asset(asset["id"], soft=True)

    # 重新添加同一 symbol
    result = await service.add_asset({"symbol": "hk00700"})
    assert result["enabled"] is True or result["enabled"] == 1
    assert result["id"] == asset["id"]  # 复用同一条记录


async def test_add_asset_active_duplicate_still_errors(service: AssetService) -> None:
    """已启用的标的重复添加仍抛 AssetExistsError。"""
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    with pytest.raises(AssetExistsError, match="已在追踪列表"):
        await service.add_asset({"symbol": "hk00700"})


async def test_search_assets(service: AssetService) -> None:
    fake = FakeProvider(
        name="fake",
        search_results=[
            {"symbol": "hk00700", "name": "腾讯控股", "market": "hk"},
            {"symbol": "hk00981", "name": "中芯国际", "market": "hk"},
        ],
    )
    svc = AssetService(providers={"structured": [fake], "news": []})
    results = await svc.search_assets("腾讯")
    assert len(results) == 2
    assert results[0]["source"] == "fake"


async def test_search_assets_with_market_filter() -> None:
    fake = FakeProvider(
        name="fake",
        search_results=[
            {"symbol": "hk00700", "name": "腾讯控股", "market": "hk"},
            {"symbol": "usTCEHY", "name": "腾讯ADR", "market": "us"},
        ],
    )
    svc = AssetService(providers={"structured": [fake], "news": []})
    results = await svc.search_assets("腾讯", market="hk")
    assert len(results) == 1
    assert results[0]["market"] == "hk"


async def test_search_assets_provider_error() -> None:
    failing = AsyncMock(spec=BaseProvider)
    failing.name = "failing"
    failing.search.side_effect = Exception("连接超时")

    fake = FakeProvider(
        name="backup",
        search_results=[{"symbol": "hk00700", "name": "腾讯控股", "market": "hk"}],
    )
    svc = AssetService(providers={"structured": [failing, fake], "news": []})
    results = await svc.search_assets("腾讯")
    assert len(results) == 1
    assert results[0]["source"] == "backup"


async def test_search_assets_dedup() -> None:
    fake1 = FakeProvider(
        name="source1",
        search_results=[{"symbol": "hk00700", "name": "腾讯控股", "market": "hk"}],
    )
    fake2 = FakeProvider(
        name="source2",
        search_results=[{"symbol": "hk00700", "name": "腾讯控股", "market": "hk"}],
    )
    svc = AssetService(providers={"structured": [fake1, fake2], "news": []})
    results = await svc.search_assets("腾讯")
    assert len(results) == 1
    assert results[0]["source"] == "source1"


async def test_get_active_assets(service: AssetService) -> None:
    await service.add_asset({"symbol": "hk00700", "name": "腾讯控股"})
    await service.add_asset({"symbol": "sh600519", "name": "贵州茅台"})
    await service.add_asset({"symbol": "usAAPL", "name": "Apple"})
    service.delete_asset(2, soft=True)

    result = service.get_active_assets()
    assert len(result) == 2
    symbols = {a["symbol"] for a in result}
    assert "hk00700" in symbols
    assert "usAAPL" in symbols
    assert "sh600519" not in symbols


async def test_add_asset_sz_market(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "sz000001", "name": "平安银行"})
    assert result["market"] == "sz"


async def test_add_asset_default_asset_type(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "hk00700"})
    assert result["asset_type"] == "stock"


async def test_add_asset_custom_asset_type(service: AssetService) -> None:
    result = await service.add_asset({"symbol": "hk02800", "asset_type": "etf"})
    assert result["asset_type"] == "etf"


async def test_add_asset_bare_code_with_market_sh(service: AssetService) -> None:
    """裸代码 600519 + market=sh → 自动拼接为 sh600519。"""
    result = await service.add_asset({"symbol": "600519", "market": "sh", "name": "贵州茅台"})
    assert result["symbol"] == "sh600519"
    assert result["market"] == "sh"


async def test_add_asset_bare_code_with_market_sz(service: AssetService) -> None:
    """裸代码 300750 + market=sz → 自动拼接为 sz300750。"""
    result = await service.add_asset({"symbol": "300750", "market": "sz", "name": "宁德时代"})
    assert result["symbol"] == "sz300750"
    assert result["market"] == "sz"


async def test_add_asset_bare_code_without_market_is_error(service: AssetService) -> None:
    """裸代码 300750 且无 market → 报错并提示正确格式。"""
    with pytest.raises(ValueError, match="无法识别代码.*请使用带市场前缀"):
        await service.add_asset({"symbol": "300750"})


async def test_add_asset_prefixed_symbol_ignores_market(service: AssetService) -> None:
    """已带前缀的 sz300750 + market=sh → 保持 sz 前缀（已带前缀时不覆盖）。"""
    result = await service.add_asset({"symbol": "sz300750", "market": "sh", "name": "宁德时代"})
    assert result["symbol"] == "sz300750"
    assert result["market"] == "sz"


# ── search_assets 测试 ─────────────────────────────────────────────


async def test_search_external_results_mark_already_tracked(
    service: AssetService,
) -> None:
    """外部 Provider 返回的结果，若已在本地追踪，already_tracked=True。"""
    # 先添加 sz300750
    await service.add_asset({"symbol": "sz300750", "name": "宁德时代"})

    # 替换 fake provider，让它返回 sz300750
    provider = service._providers["structured"][0]
    provider._search_results = [
        {"symbol": "sz300750", "name": "宁德时代", "market": "sz"},
    ]

    result = await service.search_assets("宁德")
    assert len(result) == 1
    assert result[0]["symbol"] == "sz300750"
    assert result[0]["already_tracked"] is True
    assert result[0]["source"] == "fake"


async def test_search_falls_back_to_local_when_external_empty(
    service: AssetService,
) -> None:
    """外部结果为空时，本地 tracked_assets 模糊匹配也回显。"""
    await service.add_asset({"symbol": "sz300750", "name": "宁德时代"})
    provider = service._providers["structured"][0]
    provider._search_results = []

    result = await service.search_assets("宁德")
    assert any(r["symbol"] == "sz300750" and r["source"] == "local" for r in result)
    assert all(r["already_tracked"] for r in result if r["source"] == "local")


async def test_search_dedupes_external_and_local(service: AssetService) -> None:
    """外部和本地都匹配到同一 symbol 时，结果只出现 1 次（优先外部 source）。"""
    await service.add_asset({"symbol": "sz300750", "name": "宁德时代"})
    provider = service._providers["structured"][0]
    provider._search_results = [
        {"symbol": "sz300750", "name": "宁德时代", "market": "sz"},
    ]

    result = await service.search_assets("宁德")
    matches = [r for r in result if r["symbol"] == "sz300750"]
    assert len(matches) == 1
    assert matches[0]["source"] == "fake"  # 外部优先


async def test_search_local_fuzzy_matches_name(service: AssetService) -> None:
    """本地匹配按 symbol 或 name 模糊匹配。"""
    await service.add_asset({"symbol": "sz300750", "name": "宁德时代"})
    provider = service._providers["structured"][0]
    provider._search_results = []

    result = await service.search_assets("时代")
    assert any(r["symbol"] == "sz300750" for r in result)


async def test_search_include_local_false_disables_fallback(
    service: AssetService,
) -> None:
    """include_local=False 时即使本地有也不回显。"""
    await service.add_asset({"symbol": "sz300750", "name": "宁德时代"})
    provider = service._providers["structured"][0]
    provider._search_results = []

    result = await service.search_assets("宁德", include_local=False)
    assert result == []
