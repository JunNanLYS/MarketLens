from backend.storage.database import get_db

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
        collected_at TIMESTAMP NOT NULL,
        UNIQUE(url)
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
]


INDEX_DDLS: list[str] = [
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_reports_symbol_date
    ON ai_reports(symbol, date(generated_at))
    """,
]


def init_db(db_path: str | None = None) -> None:
    with get_db(db_path) as conn:
        for ddl in TABLE_DDLS:
            conn.execute(ddl)
        for ddl in INDEX_DDLS:
            conn.execute(ddl)


if __name__ == "__main__":
    init_db()
