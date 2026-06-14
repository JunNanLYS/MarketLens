"""Insert methods mixin for CollectionService.

注：原 7 个旧式 _insert_kline/_insert_finance/_insert_fund_flow/
_insert_technical/_insert_dividends/_insert_profit_forecasts 已删除，
日终 6 类数据落库改用 _CollectionDailyCloseMixin._insert_daily_close 泛型实现。
"""
import sqlite3

from backend.services._collection._helpers import _save_raw_data

class _CollectionInsertMixin:
    def _insert_shareholders(
        self, conn: sqlite3.Connection, payload: dict
    ) -> tuple[int, int]:
        """股东结构 + 股东户数历史 双表单事务落盘。

        两张表共用同一份原始 raw_data + collected_at；为保证两张表数据一致性，
        必须在同一 connection、同一 commit 中写入（任一 executemany 抛错时整体回滚）。

        Returns: (top_inserted, count_inserted) 行数元组。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "shareholder", raw_json, collected_at
            )
        top_inserted = 0
        if payload["top_rows"]:
            cur = conn.executemany(
                """INSERT OR IGNORE INTO shareholders
                   (symbol, report_period, rank, name, shares, ratio, change_amount,
                    source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload["top_rows"],
            )
            top_inserted = cur.rowcount
        count_inserted = 0
        if payload["count_rows"]:
            cur = conn.executemany(
                """INSERT OR IGNORE INTO shareholder_count_history
                   (symbol, report_date, total_holders, avg_shares, source, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                payload["count_rows"],
            )
            count_inserted = cur.rowcount
        return top_inserted, count_inserted

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 _insert_* 静态方法
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_etf_basic(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "etf_basic", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_basic
               (code, date, etf_type, establish_date,
                track_index_code, track_index_name, manage_institution,
                close_price, change_pct, total_mv, shares, shares_chg,
                nav, disc, ytd_return,
                return_1m, return_3m, return_6m, return_1y, return_3y,
                max_drawdown_1m, max_drawdown_3m, max_drawdown_6m,
                max_drawdown_1y, max_drawdown_3y,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_holdings(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "etf_holdings", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO etf_holdings
               (code, constituent_code, constituent_name, ratio, date, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_nav(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "etf_nav", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO etf_nav_history
               (code, date, nav, nav_change, nav_change_pct, acc_nav, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_holders(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "etf_holders", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_holders
               (code, report_date, holder_account,
                individual_holder_share, individual_holder_ratio,
                institution_holder_share, institution_holder_ratio,
                top10_share, top10_ratio,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_chip_distribution(conn: sqlite3.Connection, payload: dict) -> int:
        """筹码成本落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn,
                payload["symbol"],
                source,
                "chip_distribution",
                raw_json,
                collected_at,
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO chip_distribution
               (symbol, date, close_price, chip_profit_rate, chip_avg_cost,
                chip_concentration_90, chip_concentration_70, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_margintrade(conn: sqlite3.Connection, payload: dict) -> int:
        """融资融券落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "margintrade", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO margintrade_data
               (symbol, date, close_price, change_pct,
                finance_value, security_value, finance_buy_value, finance_refund_value,
                trading_value, trading_value_dif, finance_value_dod, security_value_dod,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_blocktrade(conn: sqlite3.Connection, payload: dict) -> int:
        """大宗交易落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "blocktrade", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO blocktrade_data
               (symbol, date, close_price, change_pct,
                turnover_price, turnover_value, close_discount_rate,
                buy_department, sell_department, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_lhb(conn: sqlite3.Connection, payload: dict) -> int:
        """龙虎榜落库。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "lhb", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO lhb_data
               (symbol, date, name, close_price, change_pct, net_buy_amount,
                buy_department, sell_department, reason, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_ipo_exdiv(conn: sqlite3.Connection, payload: dict) -> int:
        """港美 IPO + exdiv 统一落库（共用 ipo_exdiv_calendar 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn,
                payload.get("symbol"),
                source,
                "ipo_exdiv",
                raw_json,
                collected_at,
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO ipo_exdiv_calendar
               (event_type, event_date, symbol, name, market, stage,
                price, listing_date, sgrq, ssrq,
                ex_div_date, pay_date, report_end_date,
                dividend_per_share, currency, dividend_plan,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_us_financials(conn: sqlite3.Connection, payload: dict) -> int:
        """美股/港股财务 统一落库（共用 us_financials 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "us_financial", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO us_financials
               (symbol, end_date, period_type, currency, period_mark,
                revenue, net_income, gross_profit, operating_income,
                ebitda, ebit, basic_eps, diluted_eps,
                total_assets, total_liabilities, total_equity,
                operating_cashflow, investing_cashflow, financing_cashflow, capex,
                raw_json, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_sector_quotes(conn: sqlite3.Connection, payload: dict) -> int:
        """板块首页/热门板块 统一落库（共用 sector_daily_quote 表）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, None, source, "sector_quote", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO sector_daily_quote
               (name, date, sector_type, symbol,
                change_pct, turnover_rate, change_pct_5d, change_pct_20d,
                lead_stock, main_net_inflow, main_net_inflow_5d, up_down_ratio,
                rank, zxj, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_etf_financial(conn: sqlite3.Connection, payload: dict) -> int:
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "etf_financial", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO etf_financial
               (code, date, total_assets, stock_ratio, bond_ratio,
                commodity_ratio, fund_ratio, key_asset_ratio,
                source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_minute_klines(conn: sqlite3.Connection, payload: dict) -> int:
        """分时数据落库（抽 helper 配套 staticmethod）。"""
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "minute", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        conn.executemany(
            """INSERT OR IGNORE INTO minute_klines
               (symbol, time, price, volume, avg_price, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return len(payload["rows"])
    @staticmethod
    def _insert_dividends(conn: sqlite3.Connection, payload: dict) -> int:
        """批量插入分红记录，INSERT OR IGNORE 去重。

        Returns: 实际写入行数（SQLite executemany 的 rowcount）。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "dividend", raw_json, collected_at
            )
        if not payload["rows"]:
            return 0
        cur = conn.executemany(
            """INSERT OR IGNORE INTO dividends
               (symbol, ex_date, cash_dividend, share_bonus,
                record_date, announce_date, dividend_year, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["rows"],
        )
        return cur.rowcount

    @staticmethod
    def _insert_profit_forecasts(conn: sqlite3.Connection, payload: dict) -> int:
        """单条业绩预告插入，INSERT OR IGNORE 去重。

        Returns: 实际写入行数（0 或 1）。
        """
        for source, raw_json, collected_at in payload["raw_packets"]:
            _save_raw_data(
                conn, payload["symbol"], source, "reserve", raw_json, collected_at
            )
        if payload["row"] is None:
            return 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO profit_forecasts
               (symbol, report_period, forecast_type, profit_lower, profit_upper,
                change_lower, change_upper, summary, source, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            payload["row"],
        )
        return cur.rowcount

