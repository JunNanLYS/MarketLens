"""Database schema initialization."""

import sqlite3

import aiosqlite
from loguru import logger

from backend.storage.database import aget_db

TABLE_DDLS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS tracked_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        market TEXT NOT NULL,
        asset_type TEXT NOT NULL DEFAULT 'stock',
        enabled BOOLEAN NOT NULL DEFAULT 1,
        tags TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL,
        change REAL,
        change_pct REAL,
        open REAL,
        high REAL,
        low REAL,
        prev_close REAL,
        volume REAL,
        amount REAL,
        amplitude REAL,
        turnover_rate REAL,
        high_52w REAL,
        low_52w REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, collected_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kline_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        change_pct REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_period TEXT NOT NULL,
        revenue REAL,
        revenue_yoy REAL,
        net_profit REAL,
        net_profit_yoy REAL,
        eps REAL,
        roe REAL,
        debt_ratio REAL,
        gross_margin REAL,
        net_margin REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, report_period)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fund_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        main_net_inflow REAL,
        super_large_net_inflow REAL,
        large_net_inflow REAL,
        medium_net_inflow REAL,
        small_net_inflow REAL,
        net_inflow_ratio REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS technical_indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        ma5 REAL,
        ma10 REAL,
        ma20 REAL,
        ma60 REAL,
        macd_dif REAL,
        macd_dea REAL,
        macd_histogram REAL,
        rsi6 REAL,
        rsi14 REAL,
        boll_upper REAL,
        boll_middle REAL,
        boll_lower REAL,
        volume_ma5 REAL,
        volume_ma20 REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        source TEXT NOT NULL,
        url TEXT,
        content TEXT,
        summary TEXT,
        published_at TIMESTAMP,
        sentiment TEXT,
        sectors TEXT,
        importance TEXT,
        related_symbols TEXT,
        confidence REAL,
        sentiment_reason TEXT,
        collected_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        confidence REAL NOT NULL,
        risk_level TEXT NOT NULL,
        summary TEXT,
        bullish_reasons TEXT,
        bearish_reasons TEXT,
        key_risks TEXT,
        data_used TEXT,
        generated_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TIMESTAMP NOT NULL,
        finished_at TIMESTAMP,
        error_message TEXT,
        affected_assets INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        source TEXT NOT NULL,
        data_type TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        collected_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        broker TEXT,
        currency TEXT NOT NULL DEFAULT 'CNY',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        symbol TEXT NOT NULL,
        type TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        fee REAL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'CNY',
        trade_date TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS minute_klines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        time TEXT NOT NULL,
        price REAL,
        volume REAL,
        avg_price REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, time, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dividends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        ex_date TEXT NOT NULL,
        cash_dividend REAL,
        share_bonus REAL,
        record_date TEXT,
        announce_date TEXT,
        dividend_year INTEGER,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, ex_date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profit_forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_period TEXT NOT NULL,
        forecast_type TEXT NOT NULL,
        profit_lower REAL,
        profit_upper REAL,
        change_lower REAL,
        change_upper REAL,
        summary TEXT,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, report_period, forecast_type, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shareholders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_period TEXT NOT NULL,
        rank INTEGER,
        name TEXT,
        shares REAL,
        ratio REAL,
        change_amount REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, report_period, rank, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shareholder_count_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        total_holders INTEGER,
        avg_shares REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, report_date, source)
    )
    """,
    # ------------------------------------------------------------------
    # 阶段 14：ETF 全套（5 张表）
    # westock CLI etf / etf-holdings / etf-nav / etf-holders / etf-financial
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS etf_basic (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        date TEXT NOT NULL,
        etf_type TEXT,
        establish_date TEXT,
        track_index_code TEXT,
        track_index_name TEXT,
        manage_institution TEXT,
        close_price REAL,
        change_pct REAL,
        total_mv REAL,
        shares REAL,
        shares_chg REAL,
        nav REAL,
        disc REAL,
        ytd_return REAL,
        return_1m REAL,
        return_3m REAL,
        return_6m REAL,
        return_1y REAL,
        return_3y REAL,
        max_drawdown_1m REAL,
        max_drawdown_3m REAL,
        max_drawdown_6m REAL,
        max_drawdown_1y REAL,
        max_drawdown_3y REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(code, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etf_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        constituent_code TEXT NOT NULL,
        constituent_name TEXT,
        ratio REAL,
        date TEXT NOT NULL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(code, constituent_code, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etf_nav_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        date TEXT NOT NULL,
        nav REAL,
        nav_change REAL,
        nav_change_pct REAL,
        acc_nav REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(code, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etf_holders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        report_date TEXT NOT NULL,
        holder_account INTEGER,
        individual_holder_share REAL,
        individual_holder_ratio REAL,
        institution_holder_share REAL,
        institution_holder_ratio REAL,
        top10_share REAL,
        top10_ratio REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(code, report_date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etf_financial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        date TEXT NOT NULL,
        total_assets REAL,
        stock_ratio REAL,
        bond_ratio REAL,
        commodity_ratio REAL,
        fund_ratio REAL,
        key_asset_ratio REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(code, date, source)
    )
    """,
    # ------------------------------------------------------------------
    # 阶段 8 修正：板块首页数据（sector_daily_quote）
    # westock CLI board / hot board 输出——行业/概念涨幅榜 + 行业资金流入
    # UNIQUE 须含 sector_type，因同 name 跨 industry/concept/fund_flow 三类
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS sector_daily_quote (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        sector_type TEXT NOT NULL,
        symbol TEXT,
        change_pct REAL,
        turnover_rate REAL,
        change_pct_5d REAL,
        change_pct_20d REAL,
        lead_stock TEXT,
        main_net_inflow REAL,
        main_net_inflow_5d REAL,
        up_down_ratio REAL,
        rank INTEGER,
        zxj REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(name, date, sector_type, source)
    )
    """,
    # ------------------------------------------------------------------
    # 阶段 15：港美股财务（us_financials）
    # westock CLI finance usAAPL（默认 income/balance/cashflow 3 表）
    # westock CLI finance hk<sym> --type zhsy/zcfz/xjll
    # UNIQUE 含 period_type 区分 annual/quarter，含 currency 区分 USD/HKD
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS us_financials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        end_date TEXT NOT NULL,
        period_type TEXT NOT NULL,
        currency TEXT,
        period_mark TEXT,
        -- 利润表核心
        revenue REAL,
        net_income REAL,
        gross_profit REAL,
        operating_income REAL,
        ebitda REAL,
        ebit REAL,
        basic_eps REAL,
        diluted_eps REAL,
        -- 资产负债表核心
        total_assets REAL,
        total_liabilities REAL,
        total_equity REAL,
        -- 现金流表核心
        operating_cashflow REAL,
        investing_cashflow REAL,
        financing_cashflow REAL,
        capex REAL,
        -- 兜底
        raw_json TEXT,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, end_date, period_type, source)
    )
    """,
    # ------------------------------------------------------------------
    # 阶段 16：港美 IPO + exdiv 日历（ipo_exdiv_calendar）
    # A 股 ipo/exdiv 数据源死，仅 hk/us
    # event_type 区分 ipo / exdiv；stage 区分 ipo 各阶段
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS ipo_exdiv_calendar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        event_date TEXT NOT NULL,
        symbol TEXT,
        name TEXT,
        market TEXT NOT NULL,
        stage TEXT,
        price REAL,
        listing_date TEXT,
        sgrq TEXT,
        ssrq TEXT,
        ex_div_date TEXT,
        pay_date TEXT,
        report_end_date TEXT,
        dividend_per_share REAL,
        currency TEXT,
        dividend_plan TEXT,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(event_type, event_date, symbol, source)
    )
    """,
    # ------------------------------------------------------------------
    # 阶段 17：筹码/融资融券/大宗/龙虎榜（4 张表）
    # westock CLI:
    #   - chip sh600519      → 筹码成本 (仅 sh/sz/bj)
    #   - margintrade sh600519 → 融资融券 (仅 sh/sz)
    #   - blocktrade sh600519  → 大宗交易 (仅 sh/sz，需 --date)
    #   - lhb sh600519        → 龙虎榜 (仅 sh/sz，需 --date)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS chip_distribution (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        close_price REAL,
        chip_profit_rate REAL,
        chip_avg_cost REAL,
        chip_concentration_90 REAL,
        chip_concentration_70 REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS margintrade_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        close_price REAL,
        change_pct REAL,
        finance_value REAL,
        security_value REAL,
        finance_buy_value REAL,
        finance_refund_value REAL,
        trading_value REAL,
        trading_value_dif REAL,
        finance_value_dod REAL,
        security_value_dod REAL,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS blocktrade_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        close_price REAL,
        change_pct REAL,
        turnover_price REAL,
        turnover_value REAL,
        close_discount_rate REAL,
        buy_department TEXT,
        sell_department TEXT,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lhb_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        name TEXT,
        close_price REAL,
        change_pct REAL,
        net_buy_amount REAL,
        buy_department TEXT,
        sell_department TEXT,
        reason TEXT,
        source TEXT,
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, date, source)
    )
    """,
]

INDEX_DDLS: list[str] = [
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_reports_symbol_date
    ON ai_reports(symbol, date(generated_at))
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_raw_data_symbol_type
    ON raw_data(symbol, data_type)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_run_logs_task_name
    ON run_logs(task_name, started_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_news_items_published_at
    ON news_items(published_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol_collected
    ON market_quotes(symbol, collected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fund_flows_symbol_date
    ON fund_flows(symbol, date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_financial_reports_symbol
    ON financial_reports(symbol, collected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_account_symbol
    ON transactions(account_id, symbol, trade_date, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tracked_assets_enabled
    ON tracked_assets(enabled)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_news_items_url
    ON news_items(url)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_news_items_url_unique
    ON news_items(url) WHERE url IS NOT NULL AND url != ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_deleted_at
    ON transactions(deleted_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_minute_klines_symbol_time
    ON minute_klines(symbol, time DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_dividends_symbol_exdate
    ON dividends(symbol, ex_date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_profit_forecasts_symbol_period
    ON profit_forecasts(symbol, report_period DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_shareholders_symbol_period
    ON shareholders(symbol, report_period DESC, rank)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_shareholder_count_history_symbol_date
    ON shareholder_count_history(symbol, report_date DESC)
    """,
    # 阶段 14: ETF 表索引
    """
    CREATE INDEX IF NOT EXISTS idx_etf_basic_code_date
    ON etf_basic(code, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_etf_holdings_code_date
    ON etf_holdings(code, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_etf_nav_history_code_date
    ON etf_nav_history(code, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_etf_holders_code_report
    ON etf_holders(code, report_date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_etf_financial_code_date
    ON etf_financial(code, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sector_daily_quote_date_type
    ON sector_daily_quote(date DESC, sector_type)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_us_financials_symbol_period
    ON us_financials(symbol, end_date DESC, period_type)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ipo_exdiv_calendar_date_type
    ON ipo_exdiv_calendar(event_date DESC, event_type)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chip_distribution_symbol_date
    ON chip_distribution(symbol, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_margintrade_symbol_date
    ON margintrade_data(symbol, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_blocktrade_symbol_date
    ON blocktrade_data(symbol, date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_lhb_symbol_date
    ON lhb_data(symbol, date DESC)
    """,
    # 阶段 14/15: cleanup 任务按 collected_at 删除时需要的单列索引
    # UNIQUE(code, date, source) 等隐式索引最左列为 code/symbol，无法加速 collected_at 过滤
    """
    CREATE INDEX IF NOT EXISTS idx_etf_basic_collected_at
    ON etf_basic(collected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_etf_holdings_collected_at
    ON etf_holdings(collected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_us_financials_collected_at
    ON us_financials(collected_at DESC)
    """,
    # raw_data 由 cleanup 任务按 collected_at 删除（保留 30 天），
    # 此前仅有 (symbol, data_type) 复合索引，最左列不命中 collected_at 过滤。
    # 补单列索引加速滚动清理，与 etf_basic / etf_holdings / us_financials 保持一致风格。
    """
    CREATE INDEX IF NOT EXISTS idx_raw_data_collected_at
    ON raw_data(collected_at DESC)
    """,
]


RAW_DATA_TABLE_DDL = """
CREATE TABLE raw_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    source TEXT NOT NULL,
    data_type TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    collected_at TIMESTAMP NOT NULL
)
"""


async def init_db(db_path: str | None = None) -> None:
    async with aget_db(db_path) as conn:
        for ddl in TABLE_DDLS:
            await conn.execute(ddl)
        for ddl in INDEX_DDLS:
            await conn.execute(ddl)
        await conn.commit()
        await _migrate_raw_data_symbol_nullable(conn)
        await _migrate_news_items_add_sectors(conn)
        # news_items 新增 confidence + sentiment_reason
        await _migrate_news_items_add_confidence_reason(conn)


def init_db_sync(db_path: str | None = None) -> None:
    from backend.storage.database import get_db

    with get_db(db_path) as conn:
        for ddl in TABLE_DDLS:
            conn.execute(ddl)
        for ddl in INDEX_DDLS:
            conn.execute(ddl)
        conn.commit()
        _migrate_raw_data_symbol_nullable_sync(conn)
        _migrate_news_items_add_sectors_sync(conn)
        # news_items 新增 confidence + sentiment_reason
        _migrate_news_items_add_confidence_reason_sync(conn)


def _raw_data_symbol_is_not_null_sync(conn: sqlite3.Connection) -> bool:
    """用 PRAGMA table_info 检查 raw_data.symbol 是否仍带 NOT NULL 约束。"""
    rows = conn.execute("PRAGMA table_info(raw_data)").fetchall()
    for row in rows:
        if row["name"] == "symbol":
            return bool(row["notnull"])
    return False


def _migrate_raw_data_symbol_nullable_sync(conn: sqlite3.Connection) -> None:
    """迁移：解除 raw_data.symbol 的 NOT NULL 约束。"""
    if not _raw_data_symbol_is_not_null_sync(conn):
        return

    foreign_keys_enabled = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    transaction_started = False
    try:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        transaction_started = True
        conn.execute("ALTER TABLE raw_data RENAME TO raw_data__notnull_backup")
        conn.execute(RAW_DATA_TABLE_DDL)
        conn.execute(
            """INSERT INTO raw_data (id, symbol, source, data_type, raw_json, collected_at)
               SELECT id, symbol, source, data_type, raw_json, collected_at
               FROM raw_data__notnull_backup"""
        )
        conn.execute("DROP TABLE raw_data__notnull_backup")
        conn.execute("COMMIT")
        transaction_started = False
    except Exception:
        if transaction_started:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                logger.warning("raw_data 迁移回滚失败（同步）")
        raise
    finally:
        conn.execute(
            f"PRAGMA foreign_keys={'ON' if foreign_keys_enabled else 'OFF'}"
        )

    logger.info("raw_data.symbol 已迁移为可空（重建表完成）")


async def _raw_data_symbol_is_not_null(conn: aiosqlite.Connection) -> bool:
    """用 PRAGMA table_info 检查 raw_data.symbol 是否仍带 NOT NULL 约束。"""
    cursor = await conn.execute("PRAGMA table_info(raw_data)")
    rows = await cursor.fetchall()
    for row in rows:
        if row["name"] == "symbol":
            return bool(row["notnull"])
    return False


async def _migrate_raw_data_symbol_nullable(conn: aiosqlite.Connection) -> None:
    """异步版 raw_data.symbol 可空迁移。"""
    if not await _raw_data_symbol_is_not_null(conn):
        return

    foreign_keys_enabled = bool((await (await conn.execute("PRAGMA foreign_keys")).fetchone())[0])
    transaction_started = False
    try:
        if foreign_keys_enabled:
            await conn.execute("PRAGMA foreign_keys=OFF")
        await conn.execute("BEGIN")
        transaction_started = True
        await conn.execute("ALTER TABLE raw_data RENAME TO raw_data__notnull_backup")
        await conn.execute(RAW_DATA_TABLE_DDL)
        await conn.execute(
            """INSERT INTO raw_data (id, symbol, source, data_type, raw_json, collected_at)
               SELECT id, symbol, source, data_type, raw_json, collected_at
               FROM raw_data__notnull_backup"""
        )
        await conn.execute("DROP TABLE raw_data__notnull_backup")
        await conn.execute("COMMIT")
        transaction_started = False
    except Exception:
        if transaction_started:
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                logger.warning("raw_data 迁移回滚失败（异步）")
        raise
    finally:
        await conn.execute(
            f"PRAGMA foreign_keys={'ON' if foreign_keys_enabled else 'OFF'}"
        )

    logger.info("raw_data.symbol 已迁移为可空（重建表完成）")

# ---------------------------------------------------------------------------
# 迁移：news_items 新增 sectors 列（TEXT，JSON 数组）
# ---------------------------------------------------------------------------


def _news_items_has_sectors_sync(conn: sqlite3.Connection) -> bool:
    """检查 news_items 表是否已有 sectors 列。"""
    rows = conn.execute("PRAGMA table_info(news_items)").fetchall()
    return any(row["name"] == "sectors" for row in rows)


def _migrate_news_items_add_sectors_sync(conn: sqlite3.Connection) -> None:
    """迁移：为 news_items 添加 sectors 列。"""
    if _news_items_has_sectors_sync(conn):
        return
    conn.execute("ALTER TABLE news_items ADD COLUMN sectors TEXT")
    conn.commit()
    logger.info("news_items.sectors 列已添加（ALTER TABLE 完成）")


async def _news_items_has_sectors(conn: aiosqlite.Connection) -> bool:
    """异步版：检查 news_items 表是否已有 sectors 列。"""
    cursor = await conn.execute("PRAGMA table_info(news_items)")
    rows = await cursor.fetchall()
    return any(row["name"] == "sectors" for row in rows)


async def _migrate_news_items_add_sectors(conn: aiosqlite.Connection) -> None:
    """异步版迁移：为 news_items 添加 sectors 列。"""
    if await _news_items_has_sectors(conn):
        return
    await conn.execute("ALTER TABLE news_items ADD COLUMN sectors TEXT")
    await conn.commit()
    logger.info("news_items.sectors 列已添加（ALTER TABLE 完成）")


# ---------------------------------------------------------------------------
# 迁移：news_items 新增 confidence + sentiment_reason 列
# confidence REAL —— 情感置信度（0~1 浮点）
# sentiment_reason TEXT —— 情感判定理由
# SQLite 单条 ALTER 一次只能加一列，因此拆为两条独立 ALTER
# ---------------------------------------------------------------------------


def _news_items_has_confidence_sync(conn: sqlite3.Connection) -> bool:
    """检查 news_items 表是否已有 confidence 列。"""
    rows = conn.execute("PRAGMA table_info(news_items)").fetchall()
    return any(row["name"] == "confidence" for row in rows)


def _news_items_has_sentiment_reason_sync(conn: sqlite3.Connection) -> bool:
    """检查 news_items 表是否已有 sentiment_reason 列。"""
    rows = conn.execute("PRAGMA table_info(news_items)").fetchall()
    return any(row["name"] == "sentiment_reason" for row in rows)


def _migrate_news_items_add_confidence_reason_sync(conn: sqlite3.Connection) -> None:
    """迁移：为 news_items 添加 confidence 和 sentiment_reason 列（SQLite 一次一列）。"""
    if not _news_items_has_confidence_sync(conn):
        conn.execute("ALTER TABLE news_items ADD COLUMN confidence REAL")
        conn.commit()
        logger.info("news_items.confidence 列已添加（ALTER TABLE 完成）")
    if not _news_items_has_sentiment_reason_sync(conn):
        conn.execute("ALTER TABLE news_items ADD COLUMN sentiment_reason TEXT")
        conn.commit()
        logger.info("news_items.sentiment_reason 列已添加（ALTER TABLE 完成）")


async def _news_items_has_confidence(conn: aiosqlite.Connection) -> bool:
    """异步版：检查 news_items 表是否已有 confidence 列。"""
    cursor = await conn.execute("PRAGMA table_info(news_items)")
    rows = await cursor.fetchall()
    return any(row["name"] == "confidence" for row in rows)


async def _news_items_has_sentiment_reason(conn: aiosqlite.Connection) -> bool:
    """异步版：检查 news_items 表是否已有 sentiment_reason 列。"""
    cursor = await conn.execute("PRAGMA table_info(news_items)")
    rows = await cursor.fetchall()
    return any(row["name"] == "sentiment_reason" for row in rows)


async def _migrate_news_items_add_confidence_reason(conn: aiosqlite.Connection) -> None:
    """异步版迁移：为 news_items 添加 confidence 和 sentiment_reason 列。"""
    if not await _news_items_has_confidence(conn):
        await conn.execute("ALTER TABLE news_items ADD COLUMN confidence REAL")
        await conn.commit()
        logger.info("news_items.confidence 列已添加（ALTER TABLE 完成）")
    if not await _news_items_has_sentiment_reason(conn):
        await conn.execute("ALTER TABLE news_items ADD COLUMN sentiment_reason TEXT")
        await conn.commit()
        logger.info("news_items.sentiment_reason 列已添加（ALTER TABLE 完成）")
