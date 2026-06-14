"""Extended fetch methods for CollectionService."""
import json

from loguru import logger


class _CollectionFetchExtendedMixin:
    async def _fetch_etf_info(self, symbol: str) -> dict:
        """ETF 基本信息 fetch（单条 row + raw_packets）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.etf_info(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("etf_type"),
                    data.get("establish_date"),
                    data.get("track_index_code"),
                    data.get("track_index_name"),
                    data.get("manage_institution"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("total_mv"),
                    data.get("shares"),
                    data.get("shares_chg"),
                    data.get("nav"),
                    data.get("disc"),
                    data.get("ytd_return"),
                    data.get("return_1m"),
                    data.get("return_3m"),
                    data.get("return_6m"),
                    data.get("return_1y"),
                    data.get("return_3y"),
                    data.get("max_drawdown_1m"),
                    data.get("max_drawdown_3m"),
                    data.get("max_drawdown_6m"),
                    data.get("max_drawdown_1y"),
                    data.get("max_drawdown_3y"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集 ETF 基础信息失败: {} - {}",
                    provider.name,
                    symbol,
                    e,
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_etf_holdings(self, symbol: str) -> dict:
        """ETF 成分股 fetch（多行 rows）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.etf_holdings(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(
                        (
                            symbol,
                            item.get("constituent_code", ""),
                            item.get("constituent_name"),
                            item.get("ratio"),
                            item.get("date", ""),
                            item.get("source", source),
                            item.get("collected_at", collected_at),
                        )
                    )
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集 ETF 成分股失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_etf_nav(self, symbol: str, start: str, end: str) -> dict:
        """ETF 历史净值 fetch（多行）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.etf_nav(symbol, start, end)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(
                        (
                            symbol,
                            item.get("date", ""),
                            item.get("nav"),
                            item.get("nav_change"),
                            item.get("nav_change_pct"),
                            item.get("acc_nav"),
                            item.get("source", source),
                            item.get("collected_at", collected_at),
                        )
                    )
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集 ETF 净值失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_etf_holders(self, symbol: str) -> dict:
        """ETF 持有人结构 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.etf_holders(symbol)
                if not data or not data.get("report_date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("report_date"),
                    data.get("holder_account"),
                    data.get("individual_holder_share"),
                    data.get("individual_holder_ratio"),
                    data.get("institution_holder_share"),
                    data.get("institution_holder_ratio"),
                    data.get("top10_share"),
                    data.get("top10_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集 ETF 持有人失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_chip_distribution(self, symbol: str) -> dict:
        """筹码成本 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.chip_distribution(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("chip_profit_rate"),
                    data.get("chip_avg_cost"),
                    data.get("chip_concentration_90"),
                    data.get("chip_concentration_70"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集筹码成本失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_margintrade(self, symbol: str) -> dict:
        """融资融券 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.margintrade(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("finance_value"),
                    data.get("security_value"),
                    data.get("finance_buy_value"),
                    data.get("finance_refund_value"),
                    data.get("trading_value"),
                    data.get("trading_value_dif"),
                    data.get("finance_value_dod"),
                    data.get("security_value_dod"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集融资融券失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_blocktrade(self, symbol: str, date: str) -> dict:
        """大宗交易 fetch（单只 + 日期）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.blocktrade(symbol, date)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("turnover_price"),
                    data.get("turnover_value"),
                    data.get("close_discount_rate"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集大宗交易失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_lhb(self, symbol: str, date: str) -> dict:
        """龙虎榜 fetch（单只 + 日期）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.lhb(symbol, date)
                if not data:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date", date),
                    data.get("name"),
                    data.get("close_price"),
                    data.get("change_pct"),
                    data.get("net_buy_amount"),
                    data.get("buy_department"),
                    data.get("sell_department"),
                    data.get("reason"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集龙虎榜失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }

    async def _fetch_ipo_calendar(self, market: str) -> dict:
        """新股日历 fetch（market=hk/us）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.ipo_calendar(market)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集新股日历失败: {} - {}", provider.name, market, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_exdiv_calendar(self, symbol: str) -> dict:
        """除权日历 fetch（港美单只）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.exdiv_calendar(symbol)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集除权日历失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    @staticmethod
    def _ipo_exdiv_row_tuple(item: dict, source: str, collected_at: str) -> tuple:
        """统一组装 ipo_exdiv_calendar 表的 row tuple。"""
        return (
            item.get("event_type", ""),
            item.get("event_date", ""),
            item.get("symbol"),
            item.get("name"),
            item.get("market", ""),
            item.get("stage"),
            item.get("price"),
            item.get("listing_date"),
            item.get("sgrq"),
            item.get("ssrq"),
            item.get("ex_div_date"),
            item.get("pay_date"),
            item.get("report_end_date"),
            item.get("dividend_per_share"),
            item.get("currency"),
            item.get("dividend_plan"),
            item.get("source", source),
            item.get("collected_at", collected_at),
        )

    async def _fetch_us_finance(
        self, symbol: str, ftype: str = "income", num: int = 4
    ) -> dict:
        """美股财务 fetch（多期，--type income/balance/cashflow）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.us_finance(symbol, ftype=ftype, num=num)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集美股财务失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_hk_finance(
        self, symbol: str, ftype: str = "zhsy", num: int = 4
    ) -> dict:
        """港股财务 fetch（多期，--type zhsy/zcfz/xjll）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.hk_finance(symbol, ftype=ftype, num=num)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(self._us_finance_row_tuple(item, source, collected_at))
                success = len(items)
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集港股财务失败: {} - {}", provider.name, symbol, e
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    @staticmethod
    def _us_finance_row_tuple(item: dict, source: str, collected_at: str) -> tuple:
        """统一组装 us_financials 表的 row tuple。"""
        return (
            item.get("symbol", ""),
            item.get("end_date", ""),
            item.get("period_type", "annual"),
            item.get("currency"),
            item.get("period_mark"),
            item.get("revenue"),
            item.get("net_income"),
            item.get("gross_profit"),
            item.get("operating_income"),
            item.get("ebitda"),
            item.get("ebit"),
            item.get("basic_eps"),
            item.get("diluted_eps"),
            item.get("total_assets"),
            item.get("total_liabilities"),
            item.get("total_equity"),
            item.get("operating_cashflow"),
            item.get("investing_cashflow"),
            item.get("financing_cashflow"),
            item.get("capex"),
            json.dumps(item, ensure_ascii=False, default=str),
            item.get("source", source),
            item.get("collected_at", collected_at),
        )

    async def _fetch_sector_board(self) -> dict:
        """板块首页 fetch：3 张表（行业涨幅/概念涨幅/行业资金流入 Top5）合并。

        返回 {"success": int, "failed": int, "rows": list[tuple], "raw_packets": list}
        无 symbol 参数（板块是全市场级别）。
        """
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.board_sectors()
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(
                        (
                            item.get("name", ""),
                            item.get("date", ""),
                            item.get("sector_type", "industry"),
                            item.get("symbol"),
                            item.get("change_pct"),
                            item.get("turnover_rate"),
                            item.get("change_pct_5d"),
                            item.get("change_pct_20d"),
                            item.get("lead_stock"),
                            item.get("main_net_inflow"),
                            item.get("main_net_inflow_5d"),
                            item.get("up_down_ratio"),
                            item.get("rank"),
                            item.get("zxj"),
                            item.get("source", source),
                            item.get("collected_at", collected_at),
                        )
                    )
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集板块首页失败: {}", provider.name, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_sector_hot(self, limit: int = 10) -> dict:
        """热门板块 fetch（top N）。"""
        success = 0
        failed = 0
        rows: list[tuple] = []
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                items = await provider.hot_sectors(limit=limit)
                if not items:
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                for item in items:
                    rows.append(
                        (
                            item.get("name", ""),
                            item.get("date", ""),
                            item.get("sector_type", "industry"),
                            item.get("symbol"),
                            item.get("change_pct"),
                            item.get("turnover_rate"),
                            item.get("change_pct_5d"),
                            item.get("change_pct_20d"),
                            item.get("lead_stock"),
                            item.get("main_net_inflow"),
                            item.get("main_net_inflow_5d"),
                            item.get("up_down_ratio"),
                            item.get("rank"),
                            item.get("zxj"),
                            item.get("source", source),
                            item.get("collected_at", collected_at),
                        )
                    )
                success = len(items)
                break
            except Exception as e:
                logger.warning("Provider {} 采集热门板块失败: {}", provider.name, e)
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "rows": rows,
            "raw_packets": raw_packets,
        }

    async def _fetch_etf_financial(self, symbol: str) -> dict:
        """ETF 资产配置 fetch（单条）。"""
        success = 0
        failed = 0
        row: tuple | None = None
        raw_packets: list[tuple[str, str, str]] = []
        for provider in self._get_structured_providers():
            if not self._is_westock_only(provider):
                continue
            try:
                data = await provider.etf_financial(symbol)
                if not data or not data.get("date"):
                    continue
                collected_at = self._now_iso()
                source = provider.name
                raw_packets.append(
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                )
                row = (
                    symbol,
                    data.get("date"),
                    data.get("total_assets"),
                    data.get("stock_ratio"),
                    data.get("bond_ratio"),
                    data.get("commodity_ratio"),
                    data.get("fund_ratio"),
                    data.get("key_asset_ratio"),
                    data.get("source", source),
                    data.get("collected_at", collected_at),
                )
                success = 1
                break
            except Exception as e:
                logger.warning(
                    "Provider {} 采集 ETF 资产配置失败: {} - {}",
                    provider.name,
                    symbol,
                    e,
                )
                failed += 1
                continue
        return {
            "success": success,
            "failed": failed,
            "row": row,
            "raw_packets": raw_packets,
        }
