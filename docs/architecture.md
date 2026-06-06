# MarketLens 项目架构文档

> 版本: 2.0 | 日期: 2026-06-05

MarketLens 是一个**本地优先、证据驱动**的 AI 金融研究助理系统。系统围绕"追踪标的 → 自动采集数据 → 证据驱动 AI 分析 → 可视化报告"的主链路构建，所有数据持久化在本地 SQLite 之中。

本文档反映 2026-06-04 之后的最新架构（异步化、懒加载、Security 中间件、CTE、并发采集、Service 单例等重构已全部落地），与代码现状完全对齐。

---

## 1. 核心原则与技术栈

### 1.1 核心原则

| 原则 | 说明 |
|---|---|
| **本地优先** | 数据库、调度、AI 分析均在本地运行，不依赖云端服务 |
| **证据驱动** | AI 分析禁止凭空生成，必须从数据库读取真实采集数据，`data_used` 字段强制列出引用源 |
| **源失败隔离** | 单个数据源不可用不影响其他源和整体流程（捕获异常 + run_logs 记录 + 跳过） |
| **可追溯** | 每次采集同时保存原始返回（`raw_data` 表）和标准化数据 |
| **声明与实现分离** | `config.yaml` 声明数据源与参数，Provider 类实现获取逻辑，不硬编码源名/优先级 |

### 1.2 技术栈

```
后端            Python ≥ 3.13  +  FastAPI (Pydantic v2)
                asyncio + aiohttp/httpx.AsyncClient 异步采集
                aiosqlite 异步数据库连接（仅 schema 初始化使用）
                sqlite3 同步连接 + asyncio.Lock 串行化业务写入
调度            APScheduler (BackgroundScheduler)
前端            Streamlit (展示层)
存储            SQLite (WAL 模式 + foreign_keys=ON)
日志            loguru (文件)  +  run_logs 表 (持久化)
包管理          uv
数据源          westock-data-clawhub (Node.js ≥ v18 CLI 子进程)
                新浪财经 / 腾讯新闻 / RSS / NeoData (HTTP)
测试            pytest + pytest-asyncio (asyncio_mode="auto")
```

> **重要**：Node.js ≥ v18 仅在 `westock` 数据源启用时为必需；其他纯 HTTP 数据源可独立运行。

---

## 2. 目录结构

```
MarketLens/
├── config.yaml                    # 全局配置（数据源、调度、AI 阈值、安全）
├── pyproject.toml                 # 项目依赖与元数据（uv 管理）
├── CLAUDE.md                      # 项目开发规范
├── backend/
│   ├── main.py                    # FastAPI 应用入口 + SecurityHeadersMiddleware
│   ├── config.py                  # 配置加载
│   ├── utils.py                   # 公共工具（escape_like、build_fund_flow_summary 等）
│   ├── api/                       # FastAPI 路由
│   │   ├── assets.py              # /api/v1/assets 资源路由
│   │   ├── data.py                # /api/v1/data 数据查询路由
│   │   ├── news.py                # /api/v1/news 路由
│   │   ├── neodata.py             # /api/v1/neodata 路由 + verify_api_key 依赖
│   │   ├── portfolio.py           # /api/v1/accounts、/transactions、/positions
│   │   ├── reports.py             # /api/v1/reports 报告路由
│   │   └── tasks.py               # /api/v1/tasks 任务管理路由
│   ├── collectors/                # 数据采集提供者（异步）
│   │   ├── __init__.py            # PROVIDER_REGISTRY + create_providers()
│   │   ├── base.py                # BaseProvider 抽象基类
│   │   ├── westock.py             # WeStockProvider (CLI 行情/K线/财务/资金/技术/分时/分红/股东/预告)
│   │   ├── sina.py                # SinaProvider (行情/K线/财务/资金流向)
│   │   ├── sina_news.py           # SinaNewsProvider (新浪新闻)
│   │   ├── neodata.py             # NeoDataProvider (金融数据增强)
│   │   ├── neodata_client.py      # NeoDataClient (懒加载 httpx 客户端)
│   │   ├── tencent_news.py        # TencentNewsProvider
│   │   ├── tencent_news_http.py   # TencentNewsHTTPProvider
│   │   ├── search_engine.py       # SearchEngineNewsProvider
│   │   └── rss.py                 # RSSProvider
│   ├── services/                  # 业务逻辑层
│   │   ├── asset_service.py       # 追踪标的 CRUD
│   │   ├── collection_service.py  # 数据采集编排（asyncio.gather + Semaphore + WriteLock）
│   │   ├── evidence_builder.py    # 证据包组装（供 AI 消费）
│   │   ├── ai_analyzer.py         # AI 分析引擎（规则评分）
│   │   ├── report_service.py      # AI 报告生成与查询
│   │   ├── news_service.py        # 新闻采集与关联
│   │   └── portfolio_service.py   # 投资组合：账户、交易、持仓、盈亏
│   ├── storage/                   # 数据库层
│   │   ├── database.py            # 连接管理（同步 get_db + 异步 aget_db + query_run_logs）
│   │   └── schema.py              # 建表脚本（schema 唯一入口）
│   └── scheduler/                 # 定时任务
│       └── jobs.py                # SchedulerManager + _run_* 包装层（asyncio.run）
├── ui/                            # Streamlit 前端
│   ├── app.py
│   └── pages/
├── data/                          # 数据文件（SQLite DB、日志）
├── docs/                          # 项目文档
│   ├── architecture.md
│   └── api/
└── tests/                         # 测试（镜像 backend/ 目录结构）
    ├── collectors/
    ├── services/
    ├── storage/
    ├── scheduler/
    └── api/
```

### 2.1 模块边界规则

- **`ui/`** 不直接读数据库，所有数据通过 FastAPI HTTP 接口获取
- **`backend/collectors/`** 是唯一可调外部数据源的模块
- **`backend/storage/`** 是唯一可执行 `CREATE TABLE` / `ALTER TABLE` 的模块
- **`backend/scheduler/`** 是唯一可注册定时任务的模块
- **`backend/api/`** 路由层只做参数校验、鉴权、调用 service、返回 JSON，不含业务逻辑
- 新增数据源只在 `backend/collectors/` 下创建，遵循统一 Provider 接口

---

## 3. 架构分层

```
┌──────────────────────────────────────────────────────────────────┐
│                       Streamlit UI                                │
│            (app.py + pages/)   仅通过 HTTP API 通信                │
└─────────────────────────┬────────────────────────────────────────┘
                          │ HTTP (RESTful JSON, /api/v1/*)
┌─────────────────────────▼────────────────────────────────────────┐
│                    FastAPI 后端 (async)                            │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  SecurityHeadersMiddleware (XCTO/XFO/RP/HSTS/CSP)            │ │
│  │  + CORSMiddleware (config.security.cors_origins)            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ /assets  │  │  /data   │  │ /reports │  │ /portfolio /news  │  │
│  │ /tasks   │  │ /neodata │           │  │ 写端点: verify_api_key │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────────────┘  │
│       │              │              │              │                │
│  ┌────▼──────────────▼──────────────▼──────────────▼──────────────┐│
│  │  services/  (业务编排, 全部 async + 同步 IO 查询混合)            ││
│  │  AssetService / CollectionService / EvidenceBuilder /         ││
│  │  AIAnalyzer / ReportService / NewsService / PortfolioService  ││
│  └────────────────────────┬──────────────────────────────────────┘│
│                           │                                       │
│  ┌────────────────────────▼──────────────────────────────────────┐│
│  │  storage/  (get_db 同步 + aget_db 异步 + query_run_logs)      ││
│  │  Database  Schema  (SQLite WAL + FK)                          ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────┬───────────────────────────────────────┘
                           │ asyncio
┌──────────────────────────▼───────────────────────────────────────┐
│              collectors/  (外部数据采集, 全部 async)              │
│  ┌──────────┐ ┌────────┐ ┌──────┐ ┌──────────┐ ┌──────────────┐  │
│  │ WeStock  │ │  Sina  │ │  RSS │ │ Tencent  │ │  NeoData     │  │
│  │ Provider │ │Provider│ │  ... │ │ News ... │ │  SearchEngin │  │
│  └────┬─────┘ └───┬────┘ └──┬───┘ └────┬─────┘ └──────┬───────┘  │
│       │           │          │          │              │           │
│  [subprocess]  [httpx.AsyncClient 懒加载]                          │
└──────────────────────────────────────────────────────────────────┘
                           ▲
┌──────────────────────────┴───────────────────────────────────────┐
│            scheduler/  (APScheduler BackgroundScheduler)          │
│  quote 15min | daily_close 16:00 | news 60min                    │
│  | ai_report 20:00 | cleanup 3:30                                │
│  _run_* 用 asyncio.run() 隔离 FastAPI 主 loop                     │
└──────────────────────────────────────────────────────────────────┘
```

### 3.1 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| **UI** | 渲染页面，调用 API，展示数据 | 不直接读 DB，不含业务逻辑 |
| **API 路由** | 参数校验、鉴权、调用 service、返回 JSON、统一错误格式 | 不含业务逻辑，不直接调外部数据源 |
| **Services** | 业务逻辑编排、并发采集、证据构建、AI 分析、报告生成 | 不直接调外部数据源（通过 Provider 间接） |
| **Storage** | DB 连接管理（同步 + 异步）、schema 管理、数据持久化、查询辅助（CTE） | 不含业务逻辑 |
| **Collectors** | 调外部数据源（CLI/HTTP）、原始→标准化转换 | 不写业务逻辑，不直接暴露给 UI |
| **Scheduler** | 定时触发采集 & 分析任务、维护任务状态查询 | 不实现采集/分析逻辑本身 |

---

## 4. 异步化架构

### 4.1 双轨设计

经过 2026-06-04 重构，整个采集与分析路径已全面异步化。系统采用**双轨设计**：

- **FastAPI 主进程**：路由 handler 与 Service 方法均 `async def`，运行在 uvicorn 主事件循环中
- **Scheduler tick 包装层**：`_run_quote()` / `_run_daily_close()` / `_run_news()` / `_run_ai_report()` 用 `asyncio.run()` 启动独立事件循环，避免与 FastAPI 主 loop 冲突
- **Service 单例**：`_get_collection_service()` / `_get_news_service()` 模块级懒加载单例，跨 tick 复用 Service 对象（不复用 loop 或 connection）

```python
# scheduler/jobs.py 中的典型模式
def _run_quote() -> None:
    try:
        logger.info("定时任务触发: quote")
        asyncio.run(_get_collection_service().collect_quotes())
    except Exception:
        logger.exception("定时任务执行异常: quote")
```

### 4.2 并发模式

采集路径在不同抽象层使用不同并发原语，平衡吞吐与安全：

| 层级 | 并发原语 | 用途 | 数值 |
|---|---|---|---|
| Provider 内部 | `asyncio.Semaphore` | 限制对下游 CLI/HTTP 的并发请求 | westock `_QUOTE_CONCURRENCY=5` / neodata 5 |
| Service 层（quote） | `asyncio.gather` + `Semaphore(10)` | 跨标的并发采集 | 同一时间最多 10 个标的 |
| Service 层（daily_close） | `asyncio.gather` + `Semaphore(10)` | 跨标的并发 + 单标的 4 类数据并行 | 同上 |
| SQLite 写入 | `threading.Lock` + 同步 `sqlite3` | 多协程串行化 INSERT/DELETE | 全局唯一 `_WRITE_LOCK` |
| 读端点 | 同步 `sqlite3` 上下文管理器 | 高并发 GET 请求 | 无锁 |

**关键约束**：SQLite 同步连接在同一进程内不支持多协程并发写，因此 `CollectionService` 内部使用 `_WRITE_LOCK` 串行化所有写入段。采集请求（IO 阶段）可并发，但所有 `INSERT/DELETE/COMMIT` 必须在锁内。

**为何选 `threading.Lock` 而非 `asyncio.Lock`**：scheduler tick 用 `asyncio.run()` 每次创建新事件循环，`asyncio.Lock()` 首次 `acquire` 时绑定当前 loop，跨 tick 时会失效。`threading.Lock` 跨 loop 安全且对同步 `sqlite3` 互斥语义正确。配合 `PRAGMA busy_timeout = 5000`，持有锁时 SQLite 自动等待而非 fast-fail 抛 `OperationalError`。

### 4.3 性能基线（实测）

| 指标 | 重构前 | 重构后 | 提升 |
|---|---|---|---|
| `collect_quotes` 100 标的 | 8.3 分钟 | < 2 分钟 | ~4× |
| 模块 import time | 201.8s | 0.9s | ~220× |
| 详情页 DB 查询次数 | 6 条 | 2 条 (CTE) | 3× |
| `_run_*` 启动延迟 | 复用旧事件循环冲突 | `asyncio.run()` 隔离 | 0 race condition |

> 重构前的 import 阻塞源于 Windows + Python 3.13 下 `httpx.AsyncClient()` 在模块级实例化时触发 3.8s 阻塞，10 个 Provider 累加至 38s。详见 §8 懒加载。

---

## 5. 数据流

### 5.1 采集流程

```
Scheduler 触发 _run_quote()
  → asyncio.run() 创建独立 loop
  → CollectionService.collect_quotes()
    → AssetService.get_active_assets() (从 DB 读取)
    → asyncio.gather + Semaphore(10) 跨标的分发
      → 对每个 symbol：Provider.quote() 异步请求（带 Provider 内部 Semaphore）
      → 标准化结果 → 序列化 raw_json
      → 申请 write_lock → 同步 sqlite3 INSERT OR IGNORE
      → 释放 lock
    → 写入 run_logs (task_name, status, started_at, finished_at, error_message, affected_assets)
    → 单个标的 / 单个 Provider 失败仅记录 + 跳过，不影响其他
```

### 5.2 AI 分析流程

```
Scheduler 或 POST /api/v1/reports/generate 触发
  → ReportService.generate_reports(symbols, force)
    → EvidenceBuilder.build(symbol) 逐标的
      → 查 market_quotes / kline_daily / fund_flows / financial_reports / news_items
      → 组装结构化 evidence dict (仅含真实数据)
    → AIAnalyzer.analyze(evidence_package)
      → 规则引擎按维度评分（趋势、资金、估值、情绪）
      → 输出固定 JSON schema（含 data_used 字段列出引用源）
    → 写入 ai_reports 表
      → force=False：同交易日已有报告则跳过（依赖 UNIQUE INDEX 防止重复）
      → force=True：先 DELETE 同日期报告再重新生成
```

### 5.3 用户查询流程

```
Streamlit 发起 GET /api/v1/data/quotes/{symbol}
  → API 路由（无副作用）→ CollectionService.get_quote(symbol)
  → 同步 sqlite3 SELECT (最新一条)
  → 返回 JSON → Streamlit 渲染卡片

写端点（如 POST /api/v1/reports/generate）：
  → API 路由 → verify_api_key 依赖校验 X-API-Key
  → 调用 service → 返回 200/202
```

---

## 6. 数据库 Schema

### 6.1 核心表清单（29 张）

> 第 5 轮新增 17 张表（`minute_klines` / `dividends` / `profit_forecasts` / `shareholders` / `shareholder_count_history` 5 张阶段 11/12 补充表 + `etf_basic` / `etf_holdings` / `etf_nav_history` / `etf_holders` / `etf_financial` 5 张阶段 14 ETF 表 + `sector_daily_quote` 阶段 8 板块首页 + `us_financials` 阶段 15 港美财务 + `ipo_exdiv_calendar` 阶段 16 港美日历 + `chip_distribution` / `margintrade_data` / `blocktrade_data` / `lhb_data` 阶段 17 4 张表）。DDL 集中在 `backend/storage/schema.py::TABLE_DDLS`；新增/重命名字段需同步本节。

| 表名 | 用途 | 关键字段 | 唯一约束 / 索引 |
|---|---|---|---|
| `tracked_assets` | 用户追踪标的 | symbol, name, market, asset_type, enabled, tags | `UNIQUE(symbol)` + `idx_tracked_assets_enabled` |
| `market_quotes` | 实时行情快照 | symbol, price, change_pct, volume, amount, collected_at | `UNIQUE(symbol, collected_at)` + `idx_market_quotes_symbol_collected` |
| `kline_daily` | 日 K 线 | symbol, date, OHLCV, change_pct | `UNIQUE(symbol, date)` |
| `financial_reports` | A 股财务报表 | symbol, report_period, revenue, net_profit, eps, roe, gross_margin, debt_ratio, net_margin | `UNIQUE(symbol, report_period)` + `idx_financial_reports_symbol` |
| `fund_flows` | A 股资金流向 | symbol, date, main_net_inflow, super_large/large/medium/small, net_inflow_ratio | `UNIQUE(symbol, date)` + `idx_fund_flows_symbol_date` |
| `technical_indicators` | 技术指标 | symbol, date, MA5/10/20/60, MACD(DIF/DEA/histogram), RSI(6/14), BOLL, volume_ma5/20 | `UNIQUE(symbol, date)` |
| `news_items` | 新闻/公告/研报 | title, source, url, content, summary, sentiment, importance, related_symbols, published_at | `UNIQUE INDEX idx_news_items_url_unique (url) WHERE url IS NOT NULL AND url != ''` + `idx_news_items_published_at` |
| `ai_reports` | AI 分析报告 | symbol, action, confidence, risk_level, summary, bullish_reasons, bearish_reasons, key_risks, data_used, generated_at | `UNIQUE INDEX idx_ai_reports_symbol_date ON (symbol, date(generated_at))` |
| `run_logs` | 任务运行记录 | task_name, status, started_at, finished_at, error_message, affected_assets | `idx_run_logs_task_name (task_name, started_at DESC)` |
| `raw_data` | 原始采集数据（审计） | symbol(可空), source, data_type, raw_json, collected_at | `idx_raw_data_symbol_type (symbol, data_type)` |
| `accounts` | 交易账户 | name, broker, currency, notes, deleted_at | `UNIQUE(name)` |
| `transactions` | 交易记录 | account_id(FK→accounts), symbol, type(buy/sell/dividend/split), quantity, price, fee, currency, trade_date | `idx_transactions_account_symbol` + `idx_transactions_deleted_at` |
| `minute_klines` | 分钟 K 线（1/5/15/30/60/120m） | symbol, time, price, volume, avg_price, source | `UNIQUE(symbol, time, source)` + `idx_minute_klines_symbol_time` |
| `dividends` | 分红/送股 | symbol, ex_date, cash_dividend, share_bonus, record_date, announce_date, dividend_year, source | `UNIQUE(symbol, ex_date, source)` + `idx_dividends_symbol_exdate` |
| `profit_forecasts` | 业绩预告 | symbol, report_period, forecast_type, profit_lower/upper, change_lower/upper, summary, source | `UNIQUE(symbol, report_period, forecast_type, source)` + `idx_profit_forecasts_symbol_period` |
| `shareholders` | 前 N 大股东 | symbol, report_period, rank, name, shares, ratio, change_amount, source | `UNIQUE(symbol, report_period, rank, source)` + `idx_shareholders_symbol_period` |
| `shareholder_count_history` | 股东人数历史 | symbol, report_date, total_holders, avg_shares, source | `UNIQUE(symbol, report_date, source)` + `idx_shareholder_count_history_symbol_date` |
| `etf_basic` | ETF 基本面+净值+涨跌 | code, date, etf_type, track_index_code/name, manage_institution, close_price, nav, disc, return_1m/3m/6m/1y/3y, max_drawdown_* | `UNIQUE(code, date, source)` + `idx_etf_basic_code_date` |
| `etf_holdings` | ETF 成分股 | code, constituent_code, constituent_name, ratio, date, source | `UNIQUE(code, constituent_code, date, source)` + `idx_etf_holdings_code_date` |
| `etf_nav_history` | ETF 历史净值 | code, date, nav, nav_change, nav_change_pct, acc_nav, source | `UNIQUE(code, date, source)` + `idx_etf_nav_history_code_date` |
| `etf_holders` | ETF 持有人结构 | code, report_date, holder_account, individual_holder_share/ratio, institution_holder_share/ratio, top10_share/ratio, source | `UNIQUE(code, report_date, source)` + `idx_etf_holders_code_report` |
| `etf_financial` | ETF 资产配置 | code, date, total_assets, stock_ratio, bond_ratio, commodity_ratio, fund_ratio, key_asset_ratio, source | `UNIQUE(code, date, source)` + `idx_etf_financial_code_date` |
| `sector_daily_quote` | 行业/概念板块日行情 | name, date, sector_type(industry/concept/fund_flow), symbol, change_pct, turnover_rate, change_pct_5d/20d, lead_stock, main_net_inflow, main_net_inflow_5d, up_down_ratio, rank, zxj | `UNIQUE(name, date, sector_type, source)` + `idx_sector_daily_quote_date_type` |
| `us_financials` | 港美股三表 | symbol, end_date, period_type(annual/quarter), currency(USD/HKD), period_mark, revenue, net_income, gross_profit, operating_income, ebitda, ebit, basic_eps, diluted_eps, total_assets, total_liabilities, total_equity, operating_cashflow, investing_cashflow, financing_cashflow, capex, raw_json | `UNIQUE(symbol, end_date, period_type, source)` + `idx_us_financials_symbol_period` |
| `ipo_exdiv_calendar` | 港美 IPO+除权日历 | event_type(ipo/exdiv), event_date, symbol, name, market(hk/us), stage(ipo 各阶段), price, listing_date, sgrq, ssrq, ex_div_date, pay_date, report_end_date, dividend_per_share, currency, dividend_plan, source | `UNIQUE(event_type, event_date, symbol, source)` + `idx_ipo_exdiv_calendar_date_type` |
| `chip_distribution` | 筹码分布（A 股） | symbol, date, close_price, chip_profit_rate, chip_avg_cost, chip_concentration_90, chip_concentration_70, source | `UNIQUE(symbol, date, source)` + `idx_chip_distribution_symbol_date` |
| `margintrade_data` | 融资融券（A 股） | symbol, date, close_price, change_pct, finance_value, security_value, finance_buy_value, finance_refund_value, trading_value, trading_value_dif, finance_value_dod, security_value_dod, source | `UNIQUE(symbol, date, source)` + `idx_margintrade_symbol_date` |
| `blocktrade_data` | 大宗交易（A 股） | symbol, date, close_price, change_pct, turnover_price, turnover_value, close_discount_rate, buy_department, sell_department, source | `UNIQUE(symbol, date, source)` + `idx_blocktrade_symbol_date` |
| `lhb_data` | 龙虎榜（A 股） | symbol, date, name, close_price, change_pct, net_buy_amount, buy_department, sell_department, reason, source | `UNIQUE(symbol, date, source)` + `idx_lhb_symbol_date` |
| （positions） | **持仓 — 实时计算视图** | （非持久化） | 由 portfolio_service.py 聚合计算 |

### 6.2 投资组合表与算法

#### accounts（交易账户）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | 自增主键 |
| name | TEXT | NOT NULL UNIQUE | 账户名称 |
| broker | TEXT | | 券商名称 |
| currency | TEXT | NOT NULL DEFAULT CNY | 默认币种 |
| notes | TEXT | | 备注 |
| created_at | TIMESTAMP | DEFAULT NOW | 创建时间 |
| deleted_at | TIMESTAMP | | 软删除标记 |

#### transactions（交易记录）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | 自增主键 |
| account_id | INTEGER | FK → accounts.id | 所属账户 |
| symbol | TEXT | NOT NULL | 标的代码 |
| type | TEXT | NOT NULL | 交易类型（buy / sell / dividend / split） |
| quantity | REAL | NOT NULL | 数量 |
| price | REAL | NOT NULL | 价格 |
| fee | REAL | DEFAULT 0 | 手续费 |
| currency | TEXT | NOT NULL DEFAULT CNY | 币种 |
| trade_date | DATE | NOT NULL | 交易日期 |
| notes | TEXT | | 备注 |
| created_at | TIMESTAMP | DEFAULT NOW | 创建时间 |
| updated_at | TIMESTAMP | DEFAULT NOW | 更新时间 |
| deleted_at | TIMESTAMP | | 软删除标记 |

#### positions（持仓 — 实时计算视图，非持久化表）

由 `portfolio_service.py` 实时聚合计算：

- 聚合所有 `deleted_at IS NULL` 且 `type IN (buy, sell, dividend, split)` 的交易
- 按 `(account_id, symbol)` 分组
- **均价采用加权平均法（WAC）**：每次 `buy` 重新计算均价，`sell / dividend / split` 不改变均价
- 实时从 `market_quotes` 获取最新价格计算浮动盈亏
- 卖出时校验当前持仓是否充足（`INSUFFICIENT_HOLDING` 错误）

### 6.3 Schema 变更规则

- 所有 DDL 集中在 `backend/storage/schema.py`（`TABLE_DDLS` + `INDEX_DDLS` 两个 list）
- 禁止在业务代码中执行 `ALTER TABLE` 或 `CREATE TABLE`
- 新增表后同步更新本文档的核心表清单
- 索引与表结构必须同时在 `init_db()`（异步）和 `init_db_sync()`（测试 fixture）中可见

---

## 7. 数据源架构

### 7.1 Provider 接口

`backend/collectors/base.py` 已将原 `BaseProvider` 拆分为两个 ABC，子类按需双继承：

- `StructuredProvider` — 结构化数据（行情/K线/财务/资金/技术指标），提供默认空实现的 6 个方法（`search` / `quote` / `kline` / `finance` / `fund_flow` / `technical`） + `close()` 生命周期钩子。
- `NewsProvider` — 新闻数据，提供 `fetch_news()` + `close()`。
- `BaseProvider` 保留为 `(StructuredProvider, NewsProvider)` 多继承占位，旧代码可继续继承。

```python
class StructuredProvider(ABC):
    async def search(self, keyword: str) -> list[dict]: ...      # 默认返回 []
    async def quote(self, symbols: list[str]) -> list[dict]: ... # 默认返回 []
    async def kline(self, symbol: str, period: str = "daily") -> list[dict]: ...
    async def finance(self, symbol: str) -> dict: ...            # 默认返回 {}
    async def fund_flow(self, symbol: str) -> dict: ...
    async def technical(self, symbol: str) -> dict: ...

class NewsProvider(ABC):
    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]: ...
```

新闻类 Provider（RSS / Tencent / Sina / SearchEngine）实现 `fetch_news()` 或 `search()`，结构化方法返回空 dict。

`WeStockProvider` 因同时提供结构化 + 新闻数据，需双继承两个 ABC，并额外实现 19 个扩展方法（覆盖第 5 轮新增 ETF / 板块 / 港美财务 / 日历 / 筹码 / 融资融券 / 大宗 / 龙虎榜）：

```python
class WeStockProvider(StructuredProvider, NewsProvider):
    # --- 6 个基础结构化方法 ---
    async def search(self, keyword: str) -> list[dict]: ...
    async def quote(self, symbols: list[str]) -> list[dict]: ...
    async def kline(self, symbol: str, period: str = "daily") -> list[dict]: ...
    async def finance(self, symbol: str) -> dict: ...
    async def fund_flow(self, symbol: str) -> dict: ...
    async def technical(self, symbol: str) -> dict: ...

    # --- 1 个基础新闻方法 ---
    async def fetch_news(self, symbols: list[str] | None = None) -> list[dict]: ...

    # --- 18 个扩展方法（分时/分红/股东/预告 + ETF + 板块 + 港美财务 + 日历 + 筹码等） ---
    async def minute(self, symbol: str, days: int = 1) -> list[dict]: ...                # 分钟 K 线
    async def dividend(self, symbol: str) -> list[dict]: ...                             # 分红/送股
    async def shareholder(self, symbol: str) -> dict: ...                                # 前 N 大股东
    async def reserve(self, symbol: str) -> dict: ...                                    # 业绩预告/储备
    async def etf_info(self, symbol: str) -> dict: ...                                   # ETF 基本面
    async def etf_holdings(self, symbol: str) -> list[dict]: ...                         # ETF 成分股
    async def etf_nav(self, symbol: str, start: str, end: str) -> list[dict]: ...        # ETF 净值
    async def etf_holders(self, symbol: str) -> dict: ...                                # ETF 持有人
    async def etf_financial(self, symbol: str) -> dict: ...                              # ETF 资产配置
    async def board_sectors(self) -> list[dict]: ...                                     # 行业/概念板块
    async def hot_sectors(self, limit: int = 10) -> list[dict]: ...                      # 热门板块
    async def us_finance(self, symbol: str) -> list[dict]: ...                           # 美股三表
    async def hk_finance(self, symbol: str) -> list[dict]: ...                           # 港股三表
    async def ipo_calendar(self, market: str) -> list[dict]: ...                         # 港美 IPO 日历
    async def exdiv_calendar(self, symbol: str) -> list[dict]: ...                       # 港美除权日历
    async def chip_distribution(self, symbol: str) -> dict | None: ...                  # 筹码分布
    async def margintrade(self, symbol: str) -> dict | None: ...                         # 融资融券
    async def blocktrade(self, symbol: str, date: str) -> dict | None: ...               # 大宗交易
    async def lhb(self, symbol: str, date: str) -> dict | None: ...                      # 龙虎榜
```

### 7.2 配置驱动的 Provider 实例化

`backend/collectors/__init__.py` 维护 `PROVIDER_REGISTRY` 字典，`create_providers(config)` 读取 `config.yaml` 的 `data_sources` 节动态实例化：

```python
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "WeStockProvider": WeStockProvider,
    "SinaProvider": SinaProvider,
    "RSSProvider": RSSProvider,
    "NeoDataProvider": NeoDataProvider,
    "TencentNewsProvider": TencentNewsProvider,
    "TencentNewsHTTPProvider": TencentNewsHTTPProvider,
    "SearchEngineNewsProvider": SearchEngineNewsProvider,
    "SinaNewsProvider": SinaNewsProvider,
}
```

`config.yaml` 顺序决定数据源优先级：

```yaml
data_sources:
  structured:
    - name: westock
      provider: WeStockProvider
      enabled: true
      timeout: 30
      optional: false
      params:
        command: "npx -y westock-data-clawhub@1.0.4"
  news:
    - name: sina_news
      provider: SinaNewsProvider
      enabled: true
      timeout: 15
      optional: true
```

**禁止硬编码数据源名称或优先级**。

### 7.3 容错规则

- 数据源失败 → 捕获异常 → loguru warning + run_logs 记录 → 继续下一个标的 / Provider
- `optional: true` 的源不可用时静默跳过，不阻塞主流程
- 所有外部调用（subprocess、HTTP）必须设置 `timeout`（从 `config.yaml` 读取）
- Provider 内部并发量由 Provider 自管理（避免对下游 CLI 过度施压）

---

## 8. 懒加载（Lazy Initialization）

### 8.1 为什么需要

`httpx.AsyncClient` 在 Windows + Python 3.13 上首次实例化时存在约 3.8s 的阻塞延迟（DNS / SSL 上下文初始化）。10 个 Provider 若在模块级直接 `__init__` 中创建 client，累加可达 38s，导致：

- `uvicorn` 启动阻塞
- 测试收集阶段超时
- 任何 `import backend.collectors` 都会触发全部 IO 初始化

### 8.2 实现模式

所有 HTTP Provider 采用 `_client: httpx.AsyncClient | None = None` 模式，首次调用时再创建：

```python
class XxxProvider(BaseProvider):
    def __init__(self, name: str, timeout: int = 30, params: dict | None = None, optional: bool = False) -> None:
        super().__init__(name=name, timeout=timeout, params=params, optional=optional)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.params.get("headers", {}),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
```

**已实施懒加载的 Provider**（2026-06-04 完成）：

- `rss.py` — `RSSProvider`
- `sina.py` — `SinaProvider`
- `sina_news.py` — `SinaNewsProvider`
- `tencent_news_http.py` — `TencentNewsHTTPProvider`
- `search_engine.py` — `SearchEngineNewsProvider`
- `neodata.py` + `neodata_client.py` — `NeoDataProvider` + `NeoDataClient`

**Import time 实测**：

```
重构前: 201.8s
重构后: 0.9s
```

### 8.3 生命周期

- Provider 客户端由 Service 单例持有，跨多次采集复用
- 应用关闭时（lifespan shutdown）由 Service 统一调用 `close()` 释放
- 异常路径不会泄漏未关闭 client（`try/finally` + `close()` 覆盖）

---

## 9. API 设计

### 9.1 路径与前缀

- 全部路由注册在 `/api/v1/` 前缀下
- Router 集中在 `backend/api/` 下：assets / data / news / neodata / portfolio / reports / tasks
- `GET` 无副作用；`POST/PUT/PATCH/DELETE` 为写端点

### 9.2 鉴权

- **写端点必须鉴权**：通过 `Depends(verify_api_key)` 注入
- `verify_api_key` 读取 `X-API-Key` 请求头，校验逻辑：

  ```
  优先级: MARKETLENS_API_KEY (env) > config.security.api_key
  ```

- 默认值 `marketlens-local` 仅供本地工具使用，启动时若未覆盖会记录 warning
- 写端点覆盖范围：`POST/PATCH/DELETE /assets/*` / `/accounts/*` / `/transactions/*` / `/reports/generate` / `/neodata/token` / `/tasks/trigger/*`

### 9.3 Security Headers

`SecurityHeadersMiddleware`（注册在 CORS 之前）注入 5 个安全响应头：

| Header | Value | 用途 |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | 禁止浏览器 MIME 嗅探 |
| `X-Frame-Options` | `DENY` | 禁止 iframe 嵌入 |
| `Referrer-Policy` | `no-referrer` | 出口链路不携带来源 |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | 强制 HTTPS（生产） |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'` | 保持宽松以兼容 Swagger UI |

### 9.4 统一错误响应

```json
{
  "error": "ASSET_NOT_FOUND",
  "detail": "标的 'hk00700' 未找到",
  "message": "..."  // 部分端点附加可读消息
}
```

HTTP 状态码：200 / 201 / 202 / 204 / 400 / 401 / 404 / 409 / 422 / 500 / 502 / 503

### 9.5 资源路由总览

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `GET` | `/api/v1/health` | 否 | 健康检查（db / scheduler 状态） |
| `GET` | `/api/v1/assets` | 否 | 列表（`?enabled=&market=&asset_type=&tag=&page=&page_size=`） |
| `POST` | `/api/v1/assets` | 是 | 添加追踪标的 |
| `GET` | `/api/v1/assets/{id}` | 否 | 标的详情 |
| `PATCH` | `/api/v1/assets/{id}` | 是 | 部分更新（启用/标签/备注） |
| `DELETE` | `/api/v1/assets/{id}` | 是 | 删除追踪标的（`?soft=true`） |
| `GET` | `/api/v1/assets/search` | 否 | 搜索标的（`?keyword=&market=`） |
| `GET` | `/api/v1/data/quotes/{symbol}` | 否 | 最新行情 |
| `POST` | `/api/v1/data/quotes/{symbol}/refresh` | 否 | 实时刷新单个标的行情 |
| `GET` | `/api/v1/data/quotes/{symbol}/history` | 否 | 历史行情（`?from=&to=&limit=`） |
| `GET` | `/api/v1/data/kline/{symbol}` | 否 | K 线（`?period=daily&limit=60&from=&to=`） |
| `GET` | `/api/v1/data/finance/{symbol}` | 否 | 财务摘要 |
| `GET` | `/api/v1/data/fund-flow/{symbol}` | 否 | 资金流向 |
| `GET` | `/api/v1/data/technical/{symbol}` | 否 | 技术指标 |
| `GET` | `/api/v1/news` | 否 | 新闻列表（`?symbol=&days=&sentiment=&source=&page=&page_size=`） |
| `GET` | `/api/v1/news/{id}` | 否 | 新闻详情 |
| `POST` | `/api/v1/reports/generate` | 是 | 手动触发 AI 分析 |
| `GET` | `/api/v1/reports` | 否 | 报告列表（`?action=&risk_level=&date=&page=&page_size=`） |
| `GET` | `/api/v1/reports/{symbol}` | 否 | 某标的最新报告 |
| `GET` | `/api/v1/reports/{symbol}/history` | 否 | 历史报告 |
| `GET` | `/api/v1/neodata/token-status` | 否 | NeoData token 状态查询 |
| `POST` | `/api/v1/neodata/token` | 是 | 保存 NeoData token |
| `*` | `/api/v1/accounts` | 写鉴权 | 账户 CRUD |
| `*` | `/api/v1/transactions` | 写鉴权 | 交易 CRUD |
| `GET` | `/api/v1/positions` | 否 | 实时持仓（含浮动盈亏） |
| `GET` | `/api/v1/positions/realized-pnl` | 否 | 已实现盈亏 |
| `GET` | `/api/v1/tasks/status` | 否 | 任务运行状态 |
| `POST` | `/api/v1/tasks/trigger/{task_name}` | 是 | 手动触发任务 |
| `GET` | `/api/v1/tasks/logs` | 否 | 任务日志（`?task_name=&status=&page=&page_size=`） |

### 9.6 命名规范

- 资源名用小写连字符（kebab-case）：`fund-flow` 而非 `fund_flow`
- URL 使用名词复数：`/assets` 而非 `/asset`
- 查询参数用 snake_case（与 Python 惯例一致）
- 任务名用下划线：`quote` / `daily_close` / `news` / `ai_report` / `cleanup`

---

## 10. 调度系统

### 10.1 默认任务（5 个）

| 任务 | 频率 | 说明 |
|---|---|---|
| `quote` | 每 15 分钟 | 实时行情采集（`IntervalTrigger`） |
| `daily_close` | 交易日 16:00 (cron `0 16 * * 1-5`) | K线 + 财务 + 资金流 + 技术指标 |
| `news` | 每 60 分钟 | 新闻采集 |
| `ai_report` | 每日 20:00 (cron `0 20 * * *`) | AI 报告生成 |
| `cleanup` | 每日 3:30 (cron `30 3 * * *`) | 清理 30 天前的 `raw_data` |

### 10.2 异步包装层

每个任务用 `_run_*` 包装 `asyncio.run()`，避免与 FastAPI 主 loop 冲突：

```python
def _run_quote() -> None:
    try:
        logger.info("定时任务触发: quote")
        asyncio.run(_get_collection_service().collect_quotes())
    except Exception:
        logger.exception("定时任务执行异常: quote")
```

### 10.3 Service 单例

`CollectionService` / `NewsService` 模块级懒加载单例：

```python
_collection_service: CollectionService | None = None

def _get_collection_service() -> CollectionService:
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service
```

**为何不复用 connection/loop**：sqlite3 连接不能跨 loop 复用，每次 tick 仍以 `asyncio.run()` 创建独立 loop，仅 Service 对象本身是单例（避免重建内部 Provider 链）。

### 10.4 任务规范

- 所有定时任务通过 `APScheduler BackgroundScheduler` 注册
- 每次执行写入 `run_logs`（`task_name`, `status`, `started_at`, `finished_at`, `error_message`, `affected_assets`）
- 任务必须幂等 — 重复执行不产生重复数据（通过 `UNIQUE` 约束 + `INSERT OR IGNORE`）
- 支持通过 `POST /api/v1/tasks/trigger/{name}` 手动触发
- `get_task_status()` 使用窗口函数（ROW_NUMBER OVER PARTITION BY）查询每个任务的最新一条 `run_logs`

---

## 11. AI 分析模块

### 11.1 证据驱动原则

```
禁止: AI 凭空输出"建议买入"
要求: AI 输出必须包含 data_used 字段，列出引用的数据源和采集时间
```

### 11.2 输出 Schema（不可擅自增删）

```json
{
  "symbol": "hk00700",
  "action": "watch",
  "confidence": 0.68,
  "risk_level": "medium",
  "summary": "短期趋势震荡，新闻偏正面，资金面尚未确认。",
  "bullish_reasons": ["MA5 上穿 MA20", "近 3 日主力净流入"],
  "bearish_reasons": ["MACD 高位死叉风险"],
  "key_risks": ["财报季临近，存在业绩不确定性"],
  "data_used": [
    {"source": "westock", "type": "kline_daily", "collected_at": "2026-05-31T16:05:00+08:00"},
    {"source": "westock", "type": "fund_flow", "collected_at": "2026-05-31T16:05:00+08:00"},
    {"source": "sina_rss", "type": "news", "collected_at": "2026-05-31T17:00:00+08:00"}
  ],
  "generated_at": "2026-05-31T20:00:00+08:00"
}
```

允许的 `action` 值：`buy` | `sell` | `watch` | `avoid`
允许的 `risk_level` 值：`low` | `medium` | `high`

### 11.3 分析流水线

```
EvidenceBuilder.build(symbol)
  ├── 查 market_quotes → 当前价格、涨跌幅
  ├── 查 kline_daily → 近 60 日 K 线，计算 MA/MACD/RSI
  ├── 查 fund_flows → 近 5 日资金净流向 + 汇总
  ├── 查 technical_indicators → 最新 MA/MACD/RSI/BOLL
  ├── 查 financial_reports → 最新一期财报关键指标
  └── 查 news_items → 近 7 日关联新闻，情绪聚合
      ↓
  AIAnalyzer.analyze(evidence_package)
      ↓
  ReportService.generate_reports()
  → 写入 ai_reports 表
  → UNIQUE INDEX (symbol, date(generated_at)) 防止同交易日重复
```

第一版内置保守规则型分析器（多维度加权评分）；后续可替换为真实 LLM 调用，接口不变。

---

## 12. 日志与可观测性

### 12.1 双轨日志

| 通道 | 工具 | 用途 |
|---|---|---|
| 本地文件日志 | `loguru` | 调试、开发阶段问题排查 |
| 数据库日志 | `run_logs` 表 | 运行期持久化追踪，UI 可查询展示 |

### 12.2 run_logs 表结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `task_name` | TEXT | 任务名称（quote / daily_close / news / ai_report / cleanup） |
| `status` | TEXT | success / failure |
| `started_at` | TIMESTAMP | 任务开始时间 |
| `finished_at` | TIMESTAMP | 任务结束时间 |
| `error_message` | TEXT | 失败时的错误详情 |
| `affected_assets` | INTEGER | 受影响的标的数量 |

### 12.3 日志触发点

- 数据采集开始/结束/失败
- AI 分析开始/结束/失败
- 调度任务触发
- API 异常（通过 FastAPI 全局异常 handler 统一捕获 + loguru 记录）

---

## 13. 配置管理

### 13.1 配置来源

所有可配参数集中于 `config.yaml`，代码启动时通过 `pyyaml` 加载为 dict。优先级：环境变量 > `config.yaml` > 默认值。

### 13.2 配置分类

| 配置域 | key | 说明 |
|---|---|---|
| 数据源 | `data_sources.structured[]` | 结构化数据源列表（优先级 = 顺序） |
| 数据源 | `data_sources.news[]` | 新闻源列表 |
| 数据库 | `database.path` | SQLite 文件路径 |
| 数据库 | `database.echo` | SQL 日志开关 |
| 调度 | `scheduler.timezone` | 时区（默认 Asia/Shanghai） |
| 调度 | `scheduler.tasks.*` | 各任务 interval / cron |
| AI | `ai.default_action` | 默认动作（证据不足时） |
| AI | `ai.confidence_threshold` | 置信度阈值 |
| 安全 | `security.api_key` | API Key（默认 `marketlens-local`，可被 env `MARKETLENS_API_KEY` 覆盖） |
| 安全 | `security.cors_origins` | CORS 白名单 |
| 安全 | `security.cors_methods` | 允许方法 |
| 安全 | `security.cors_headers` | 允许请求头 |

### 13.3 硬编码禁止清单

- ❌ 数据源名称/优先级
- ❌ 文件路径（DB、日志）
- ❌ 超时值
- ❌ API 密钥（明文）
- ❌ 调度频率
- ❌ 端口号（除 `config.yaml` 显式声明）

---

## 14. 错误处理策略

### 14.1 分层容错

```
数据源不可用 → 捕获异常 → run_logs 记录 → 跳过（不崩溃）
    ↓
单个标的采集失败 → 捕获异常 → run_logs 记录 → 继续下一个
    ↓
整个采集任务失败 → APScheduler 记录 → UI 显示任务状态异常
    ↓
FastAPI 异常 → 全局异常 handler → 统一 JSON 错误响应
```

### 14.2 外部调用防护

- 所有 `subprocess.run()` / `asyncio.create_subprocess_exec` 调用设置 `timeout`
- 所有 `httpx.AsyncClient` 调用设置 `timeout`（从 `config.yaml` 读取）
- Provider 内部 `asyncio.gather(..., return_exceptions=True)` 隔离单点失败

### 14.3 API 错误码

| HTTP | 错误码 | 场景 |
|---|---|---|
| 400 | `INVALID_SYMBOL` / `INVALID_INPUT` / `INSUFFICIENT_HOLDING` | 请求参数无效 / 持仓不足 |
| 401 | `UNAUTHORIZED` | 写端点缺少/错误 X-API-Key |
| 404 | `ASSET_NOT_FOUND` / `ACCOUNT_NOT_FOUND` / `TRANSACTION_NOT_FOUND` / `REPORT_NOT_FOUND` / `NEWS_NOT_FOUND` / `SYMBOL_NOT_FOUND` / `TASK_NOT_FOUND` | 资源不存在 |
| 409 | `ASSET_EXISTS` / `ACCOUNT_EXISTS` | 资源冲突 |
| 500 | `INTERNAL_ERROR` / `TRIGGER_FAILED` | 服务内部错误 |
| 502 | `REFRESH_FAILED` | 上游刷新失败 |
| 503 | `SCHEDULER_NOT_READY` | 调度器未初始化 |

---

## 15. 安全

### 15.1 Security Headers（响应层）

详见 §9.3。`SecurityHeadersMiddleware` 注册在 `CORSMiddleware` 之前，确保 preflight 401/4xx 响应也携带安全头。

### 15.2 写端点鉴权

- 鉴权依赖：`backend.api.neodata.verify_api_key`
- 注入方式：`def handler(..., _auth: None = Depends(verify_api_key))`
- 优先级：env `MARKETLENS_API_KEY` > `config.security.api_key` > 默认 `marketlens-local`
- 默认 key 启动时记录 warning（生产环境必须覆盖）

### 15.3 密钥管理

- API Key / NeoData Token 等敏感配置优先使用环境变量
- `NeoDataClient.save_token()` 接收明文 token，持久化到 DB；不写入日志
- 配置文件不入版本库的敏感字段通过 `.gitignore` 排除（或使用 `.env` + `python-dotenv`）

### 15.4 敏感数据保护

- 所有 `httpx` 请求不记录 Authorization / Cookie / API Key 头（loguru 过滤器）
- 数据库中 token 字段不进 SELECT * 列表导出
- 用户账户名/交易备注不写入 loguru 文件

### 15.5 CORS

- 默认白名单：`http://localhost:8501`, `http://127.0.0.1:8501`（Streamlit）
- 生产环境通过 `config.yaml` 的 `security.cors_origins` 显式声明
- 禁止使用通配符 `*` 与 `allow_credentials=True` 同时启用

---

## 16. 部署与运行

### 16.1 环境要求

- Python ≥ 3.13
- `uv` 包管理器
- Node.js ≥ v18（**仅** `westock` 数据源启用时必需）
- SQLite（系统自带，无需安装）

### 16.2 启动命令

```bash
# 安装依赖
uv sync

# 启动 FastAPI 后端（开发模式）
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 启动 Streamlit UI
uv run streamlit run ui/app.py
```

### 16.3 初始化与单次运行

```bash
# 初始化数据库
uv run python -m backend.storage.schema

# 手动触发采集（写端点需 X-API-Key）
curl -X POST http://localhost:8000/api/v1/tasks/trigger/quote \
  -H "X-API-Key: marketlens-local"
```

### 16.4 健康检查

```bash
curl http://localhost:8000/api/v1/health
# {"status": "ok", "database": "ok", "scheduler": "ok"}
```

### 16.5 测试

```bash
# 全部测试
uv run pytest tests/ -v

# 单文件
uv run pytest tests/services/test_collection_service.py -v

# 单个测试
uv run pytest tests/services/test_collection_service.py::test_collect_quotes_concurrent -v
```

测试使用 `pytest-asyncio` 的 `asyncio_mode = "auto"`，所有 `async def test_*` 自动被识别为协程。
