"""Database schema initialization."""

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
        importance TEXT,
        related_symbols TEXT,
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
        symbol TEXT NOT NULL,
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
]


async def init_db(db_path: str | None = None) -> None:
    async with aget_db(db_path) as conn:
        for ddl in TABLE_DDLS:
            await conn.execute(ddl)
        for ddl in INDEX_DDLS:
            await conn.execute(ddl)


def init_db_sync(db_path: str | None = None) -> None:
    from backend.storage.database import get_db
    with get_db(db_path) as conn:
        for ddl in TABLE_DDLS:
            conn.execute(ddl)
        for ddl in INDEX_DDLS:
            conn.execute(ddl)
