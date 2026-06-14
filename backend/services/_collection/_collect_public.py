"""Public collect_* methods mixin for CollectionService."""
import json

from backend.services._collection._helpers import _with_run_log


class _CollectionPublicMixin:
    async def collect_intraday(self, symbol: str, days: int = 1) -> list[dict] | None:
        """实时采集分时数据并落库。

        注：分时数据按需触发（API 主动调用），不在 daily_close 编排中拉取。
        """

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
            for item in items:
                rows.append(
                    (
                        symbol,
                        item.get("time", ""),
                        item.get("price"),
                        item.get("volume"),
                        item.get("avg_price"),
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    )
                )
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="minute",
            payload_builder=_build_payload,
            insert_fn=self._insert_minute_klines,
            provider_args={"days": days},
            error_label="分时",
        )

    @_with_run_log("shareholder_refresh")
    async def collect_shareholder(self, symbol: str) -> dict | None:
        """实时采集股东结构数据并落库（双表单事务）。"""

        def _build_payload(result, source, collected_at):
            report_period_fallback = (
                result.get("report_period") or result.get("end_date") or collected_at
            )
            top_rows: list[tuple] = []
            for sh in result["top_shareholders"]:
                top_rows.append(
                    (
                        symbol,
                        report_period_fallback,
                        sh.get("rank"),
                        sh.get("name"),
                        sh.get("shares"),
                        sh.get("ratio"),
                        sh.get("change"),
                        result.get("source", source),
                        result.get("collected_at", collected_at),
                    )
                )
            count_rows: list[tuple] = []
            for hc in result.get("holder_count_history", []):
                count_rows.append(
                    (
                        symbol,
                        hc.get("date", ""),
                        hc.get("total_holders"),
                        hc.get("avg_shares"),
                        result.get("source", source),
                        result.get("collected_at", collected_at),
                    )
                )
            return {
                "symbol": symbol,
                "top_rows": top_rows,
                "count_rows": count_rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(result, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(result):
            return bool(result) and bool(result.get("top_shareholders"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="shareholder",
            payload_builder=_build_payload,
            insert_fn=self._insert_shareholders,
            validate_fn=_validate,
            error_label="股东结构",
        )

    @_with_run_log("reserve_refresh")
    async def collect_reserve(self, symbol: str) -> dict | None:
        """实时采集业绩预告并落库。"""

        def _build_payload(result, source, collected_at):
            forecast_type = result.get("forecast_type") or "未知"
            row = (
                symbol,
                result.get("report_period"),
                forecast_type,
                result.get("profit_lower"),
                result.get("profit_upper"),
                result.get("change_lower"),
                result.get("change_upper"),
                result.get("summary"),
                result.get("source", source),
                result.get("collected_at", collected_at),
            )
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(result, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(result):
            return bool(result) and bool(result.get("report_period"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="reserve",
            payload_builder=_build_payload,
            insert_fn=self._insert_profit_forecasts,
            validate_fn=_validate,
            error_label="业绩预告",
        )

    @_with_run_log("dividend_refresh")
    async def collect_dividend(self, symbol: str) -> list[dict] | None:
        """实时采集分红记录并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
            for item in items:
                year_val = item.get("dividend_year")
                if not isinstance(year_val, int):
                    try:
                        year_val = (
                            int(str(year_val).strip())
                            if year_val is not None and str(year_val).strip()
                            else None
                        )
                    except (ValueError, TypeError):
                        year_val = None
                rows.append(
                    (
                        symbol,
                        item.get("ex_date", ""),
                        item.get("cash_dividend"),
                        item.get("share_bonus"),
                        item.get("record_date"),
                        item.get("announce_date"),
                        year_val,
                        item.get("source", source),
                        item.get("collected_at", collected_at),
                    )
                )
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="dividend",
            payload_builder=_build_payload,
            insert_fn=self._insert_dividends,
            error_label="分红记录",
        )

    async def collect_etf_info(self, symbol: str) -> dict | None:
        """采集 ETF 基本信息并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(data):
            return bool(data) and bool(data.get("date"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="etf_info",
            payload_builder=_build_payload,
            insert_fn=self._insert_etf_basic,
            validate_fn=_validate,
            error_label="ETF 基础信息",
            abort_on_invalid=True,
        )

    @_with_run_log("etf_holdings_refresh")
    async def collect_etf_holdings(self, symbol: str) -> list[dict] | None:
        """采集 ETF 成分股并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
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
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="etf_holdings",
            payload_builder=_build_payload,
            insert_fn=self._insert_etf_holdings,
            error_label="ETF 成分股",
            abort_on_invalid=True,
        )

    @_with_run_log("etf_nav_refresh")
    async def collect_etf_nav(
        self, symbol: str, start: str, end: str
    ) -> list[dict] | None:
        """采集 ETF 历史净值并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
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
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="etf_nav",
            payload_builder=_build_payload,
            insert_fn=self._insert_etf_nav,
            provider_args={"start": start, "end": end},
            error_label="ETF 净值",
            abort_on_invalid=True,
        )

    @_with_run_log("etf_holders_refresh")
    async def collect_etf_holders(self, symbol: str) -> dict | None:
        """采集 ETF 持有人结构并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(data):
            return bool(data) and bool(data.get("report_date"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="etf_holders",
            payload_builder=_build_payload,
            insert_fn=self._insert_etf_holders,
            validate_fn=_validate,
            error_label="ETF 持有人",
            abort_on_invalid=True,
        )

    @_with_run_log("chip_distribution_refresh")
    async def collect_chip_distribution(self, symbol: str) -> dict | None:
        """采集筹码成本并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(data):
            return bool(data) and bool(data.get("date"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="chip_distribution",
            payload_builder=_build_payload,
            insert_fn=self._insert_chip_distribution,
            validate_fn=_validate,
            error_label="筹码成本",
            abort_on_invalid=True,
        )

    @_with_run_log("margintrade_refresh")
    async def collect_margintrade(self, symbol: str) -> dict | None:
        """采集融资融券并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(data):
            return bool(data) and bool(data.get("date"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="margintrade",
            payload_builder=_build_payload,
            insert_fn=self._insert_margintrade,
            validate_fn=_validate,
            error_label="融资融券",
            abort_on_invalid=True,
        )

    @_with_run_log("blocktrade_refresh")
    async def collect_blocktrade(self, symbol: str, date: str) -> dict | None:
        """采集大宗交易并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="blocktrade",
            payload_builder=_build_payload,
            insert_fn=self._insert_blocktrade,
            provider_args={"date": date},
            error_label="大宗交易",
            abort_on_invalid=True,
        )

    @_with_run_log("lhb_refresh")
    async def collect_lhb(self, symbol: str, date: str) -> dict | None:
        """采集龙虎榜并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="lhb",
            payload_builder=_build_payload,
            insert_fn=self._insert_lhb,
            provider_args={"date": date},
            error_label="龙虎榜",
            abort_on_invalid=True,
        )

    @_with_run_log("ipo_calendar_refresh")
    async def collect_ipo_calendar(self, market: str) -> list[dict] | None:
        """采集新股日历（hk/us）并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
            for item in items:
                rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
            return {
                "symbol": None,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=market,
            provider_method_name="ipo_calendar",
            payload_builder=_build_payload,
            insert_fn=self._insert_ipo_exdiv,
            error_label="新股日历",
            abort_on_invalid=True,
        )

    @_with_run_log("exdiv_calendar_refresh")
    async def collect_exdiv_calendar(self, symbol: str) -> list[dict] | None:
        """采集除权日历（港美）并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
            for item in items:
                rows.append(self._ipo_exdiv_row_tuple(item, source, collected_at))
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="exdiv_calendar",
            payload_builder=_build_payload,
            insert_fn=self._insert_ipo_exdiv,
            error_label="除权日历",
            abort_on_invalid=True,
        )

    @_with_run_log("us_finance_refresh")
    async def collect_us_finance(self, symbol: str, num: int = 4) -> list[dict] | None:
        """采集美股财务（3 个 type × num 期 = 12 行）并落库。

        3 个报表类型（income / balance / cashflow）改为 asyncio.gather 并发采集，
        避免 npx 冷启动串行阻塞（单标的 3 × 2-5s = 6-15s → max(单次) ≈ 5s）。
        """

        def _build_payload(all_items, source, collected_at):
            rows: list[tuple] = []
            for item in all_items:
                rows.append(self._us_finance_row_tuple(item, source, collected_at))
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(all_items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_multi_with_lock(
            target=symbol,
            provider_method_name="us_finance",
            ftype_arg="ftype",
            payload_builder=_build_payload,
            insert_fn=self._insert_us_financials,
            provider_args={"num": num},
            ftype_values=("income", "balance", "cashflow"),
            error_label="美股财务",
        )

    @_with_run_log("hk_finance_refresh")
    async def collect_hk_finance(self, symbol: str, num: int = 4) -> list[dict] | None:
        """采集港股财务（3 个 type × num 期 = 12 行）并落库。

        3 个报表类型（zhsy 利润表 / zcfz 资产负债表 / xjll 现金流量表）改为 asyncio.gather 并发采集。
        """

        def _build_payload(all_items, source, collected_at):
            rows: list[tuple] = []
            for item in all_items:
                rows.append(self._us_finance_row_tuple(item, source, collected_at))
            return {
                "symbol": symbol,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(all_items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_multi_with_lock(
            target=symbol,
            provider_method_name="hk_finance",
            ftype_arg="ftype",
            payload_builder=_build_payload,
            insert_fn=self._insert_us_financials,
            provider_args={"num": num},
            ftype_values=("zhsy", "zcfz", "xjll"),
            error_label="港股财务",
        )

    @_with_run_log("sector_board_refresh")
    async def collect_sector_board(self) -> dict | None:
        """采集板块首页（3 张表）并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
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
            return {
                "symbol": None,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=None,
            provider_method_name="board_sectors",
            payload_builder=_build_payload,
            insert_fn=self._insert_sector_quotes,
            error_label="板块首页",
            abort_on_invalid=True,
        )

    @_with_run_log("sector_hot_refresh")
    async def collect_sector_hot(self, limit: int = 10) -> list[dict] | None:
        """采集热门板块并落库。"""

        def _build_payload(items, source, collected_at):
            rows: list[tuple] = []
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
            return {
                "symbol": None,
                "rows": rows,
                "raw_packets": [
                    (
                        source,
                        json.dumps(items, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        return await self._run_collect_with_lock(
            target=None,
            provider_method_name="hot_sectors",
            payload_builder=_build_payload,
            insert_fn=self._insert_sector_quotes,
            provider_args={"limit": limit},
            error_label="热门板块",
            abort_on_invalid=True,
        )

    @_with_run_log("etf_financial_refresh")
    async def collect_etf_financial(self, symbol: str) -> dict | None:
        """采集 ETF 资产配置并落库。"""

        def _build_payload(data, source, collected_at):
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
            return {
                "symbol": symbol,
                "row": row,
                "raw_packets": [
                    (
                        source,
                        json.dumps(data, ensure_ascii=False, default=str),
                        collected_at,
                    )
                ],
            }

        def _validate(data):
            return bool(data) and bool(data.get("date"))

        return await self._run_collect_with_lock(
            target=symbol,
            provider_method_name="etf_financial",
            payload_builder=_build_payload,
            insert_fn=self._insert_etf_financial,
            validate_fn=_validate,
            error_label="ETF 资产配置",
            abort_on_invalid=True,
        )

