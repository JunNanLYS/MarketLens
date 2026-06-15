"""Read/get methods mixin for CollectionService."""
from typing import Any

from backend.storage.database import get_db
from backend.utils import build_fund_flow_summary


class _CollectionReadMixin:
    def get_quote(self, symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT * FROM market_quotes WHERE symbol = ? ORDER BY collected_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_quote_history(
        self,
        symbol: str,
        limit: int = 100,
        from_dt: str | None = None,
        to_dt: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_dt is not None:
            conditions.append("collected_at >= ?")
            params.append(from_dt)
        if to_dt is not None:
            conditions.append("collected_at <= ?")
            params.append(to_dt)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM market_quotes WHERE {where} ORDER BY collected_at DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_kline(
        self,
        symbol: str,
        limit: int = 60,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_date is not None:
            conditions.append("date >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("date <= ?")
            params.append(to_date)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM kline_daily WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_finance(self, symbol: str, limit: int = 4) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM financial_reports WHERE symbol = ?
                   ORDER BY collected_at DESC LIMIT ?""",
                (symbol, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_fund_flow(self, symbol: str, days: int = 5) -> dict:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM fund_flows WHERE symbol = ?
                   ORDER BY date DESC LIMIT ?""",
                (symbol, days),
            ).fetchall()
        items = [dict(row) for row in rows]
        summary = build_fund_flow_summary(items) or {
            "net_flow_5d": 0,
            "trend": "无数据",
            "avg_net_inflow_ratio": 0.0,
        }
        return {"items": items, "summary": summary}

    def get_technical(self, symbol: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                """SELECT * FROM technical_indicators WHERE symbol = ?
                   ORDER BY date DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # 阶段 14：ETF 5 个 collect_* 公开方法（手动触发采集 + 落库）
    # ------------------------------------------------------------------

    def get_dividends(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询分红记录，按 ex_date 降序。

        Args:
            symbol: 标的代码。
            limit: 返回行数上限。
            source: 可选数据源过滤；None 时返回所有数据源。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM dividends WHERE {where} ORDER BY ex_date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_shareholders(
        self,
        symbol: str,
        limit: int = 10,
        source: str | None = None,
    ) -> dict:
        """查询股东结构 + 股东户数历史。

        Args:
            symbol: 标的代码。
            limit: top_shareholders 返回行数上限。
            source: 可选数据源过滤。

        Returns:
            dict 含 top_shareholders / holder_count_history 两条列表。
        """
        top_conditions: list[str] = ["symbol = ?"]
        top_params: list[Any] = [symbol]
        if source is not None:
            top_conditions.append("source = ?")
            top_params.append(source)
        top_where = " AND ".join(top_conditions)
        top_params.append(limit)
        top_sql = (
            f"SELECT * FROM shareholders WHERE {top_where} "
            f"ORDER BY report_period DESC, rank ASC LIMIT ?"
        )

        cnt_conditions: list[str] = ["symbol = ?"]
        cnt_params: list[Any] = [symbol]
        if source is not None:
            cnt_conditions.append("source = ?")
            cnt_params.append(source)
        cnt_where = " AND ".join(cnt_conditions)
        cnt_sql = (
            f"SELECT * FROM shareholder_count_history WHERE {cnt_where} "
            f"ORDER BY report_date DESC"
        )

        with get_db() as conn:
            top_rows = conn.execute(top_sql, top_params).fetchall()
            cnt_rows = conn.execute(cnt_sql, cnt_params).fetchall()
        return {
            "top_shareholders": [dict(r) for r in top_rows],
            "holder_count_history": [dict(r) for r in cnt_rows],
        }

    def get_profit_forecasts(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询业绩预告，按 report_period 降序。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM profit_forecasts WHERE {where} ORDER BY report_period DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_basic(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 基本信息（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM etf_basic WHERE {where} ORDER BY date DESC LIMIT 1"
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_etf_holdings(
        self,
        symbol: str,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        """查询 ETF 成分股（最新清单）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM etf_holdings WHERE {where} ORDER BY date DESC, ratio DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_nav(
        self,
        symbol: str,
        limit: int = 60,
        source: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """查询 ETF 历史净值。

        date 范围过滤下推到 SQL，避免"先 LIMIT N 再过滤"造成区间外的数据被静默丢弃。
        """
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        if from_date is not None:
            conditions.append("date >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("date <= ?")
            params.append(to_date)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM etf_nav_history WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_holders(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 持有人结构（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = (
            f"SELECT * FROM etf_holders WHERE {where} ORDER BY report_date DESC LIMIT 1"
        )
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_chip_distribution(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询筹码成本，按 date 降序。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = (
            f"SELECT * FROM chip_distribution WHERE {where} ORDER BY date DESC LIMIT ?"
        )
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_margintrade(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询融资融券。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM margintrade_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_blocktrade(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询大宗交易。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM blocktrade_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_lhb(
        self,
        symbol: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询龙虎榜。"""
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM lhb_data WHERE {where} ORDER BY date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_ipo_exdiv_calendar(
        self,
        event_type: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询 ipo/exdiv 日历。

        Args:
            event_type: ipo | exdiv，None 时返回所有
            market: hk | us，None 时返回所有
            symbol: 过滤特定 symbol
            limit: 返回行数上限
        """
        conditions: list[str] = []
        params: list[Any] = []
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if market is not None:
            conditions.append("market = ?")
            params.append(market)
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        sql = f"SELECT * FROM ipo_exdiv_calendar WHERE {where} ORDER BY event_date DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_us_financials(
        self,
        symbol: str,
        period_type: str | None = None,
        limit: int = 20,
        source: str | None = None,
    ) -> list[dict]:
        """查询港美股财务，按 end_date 降序。

        Args:
            symbol: 港美股代码（usAAPL / hk00700）。
            period_type: annual | quarter，None 时返回所有。
            limit: 返回行数上限。
            source: 数据源过滤。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if period_type is not None:
            conditions.append("period_type = ?")
            params.append(period_type)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = (
            f"SELECT * FROM us_financials WHERE {where} ORDER BY end_date DESC LIMIT ?"
        )
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_sector_quotes(
        self,
        sector_type: str | None = None,
        date: str | None = None,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        """查询板块行情。

        Args:
            sector_type: industry | concept | fund_flow，None 时返回所有类型
            date: YYYY-MM-DD，None 时取最新一天
            limit: 返回行数上限
            source: 数据源过滤
        """
        conditions: list[str] = []
        params: list[Any] = []
        if sector_type is not None:
            conditions.append("sector_type = ?")
            params.append(sector_type)
        if date is not None:
            conditions.append("date = ?")
            params.append(date)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions) if conditions else "1=1"
        # 取最新日期作为子查询锚点
        if date is None:
            sql = f"""
                SELECT * FROM sector_daily_quote
                WHERE date = (SELECT MAX(date) FROM sector_daily_quote)
                  AND {where}
                ORDER BY change_pct DESC
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT * FROM sector_daily_quote
                WHERE {where}
                ORDER BY change_pct DESC
                LIMIT ?
            """
        params.append(limit)
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_etf_financial(
        self,
        symbol: str,
        source: str | None = None,
    ) -> dict | None:
        """查询 ETF 资产配置（最新一条）。"""
        conditions: list[str] = ["code = ?"]
        params: list[Any] = [symbol]
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM etf_financial WHERE {where} ORDER BY date DESC LIMIT 1"
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_minute_klines(
        self,
        symbol: str,
        limit: int = 240,
        from_dt: str | None = None,
        to_dt: str | None = None,
    ) -> list[dict]:
        """查询分时 K 线，按 time 降序。

        Args:
            symbol: 标的代码。
            limit: 返回行数上限（默认 240，对应 4 小时交易时间 1 分钟 K）。
            from_dt: 起始时间（ISO 字符串，可选）。
            to_dt: 截止时间（ISO 字符串，可选）。
        """
        conditions: list[str] = ["symbol = ?"]
        params: list[Any] = [symbol]
        if from_dt is not None:
            conditions.append("time >= ?")
            params.append(from_dt)
        if to_dt is not None:
            conditions.append("time <= ?")
            params.append(to_dt)
        where = " AND ".join(conditions)
        params.append(limit)
        sql = f"SELECT * FROM minute_klines WHERE {where} ORDER BY time DESC LIMIT ?"
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
