# MarketLens 项目架构文档

## 1. 系统概述

MarketLens 是一个本地优先的 AI 金融研究助理系统，面向个人投资者与研究员。系统围绕"追踪标的 → 自动采集数据 → 证据驱动 AI 分析 → 可视化报告"的主链路构建。

### 1.1 核心原则

| 原则 | 说明 |
|---|---|
| **本地优先** | 数据库、调度、分析均在本地运行，不依赖云端服务 |
| **证据驱动** | AI 分析禁止凭空生成，必须从数据库读取真实采集数据 |
| **源失败隔离** | 单个数据源不可用不影响其他源和整体流程 |
| **可追溯** | 每次采集同时保存原始返回和标准化数据 |
| **声明与实现分离** | `config.yaml` 声明数据源与参数，Provider 类实现获取逻辑 |

### 1.2 技术栈

```
Python ≥ 3.13          FastAPI (后端 API)
SQLite                 APScheduler (定时调度)
pandas                 Streamlit (UI)
loguru                 uv (包管理)
Node.js ≥ v18          westock-data-clawhub CLI (数据源依赖)
```

---

## 2. 目录结构

```
MarketLens/
├── config.yaml                  # 全局配置（数据源、调度、AI 阈值）
├── pyproject.toml               # 项目依赖与元数据（uv 管理）
├── AGENTS.md                    # 项目开发规范
├── backend/
│   ├── main.py                  # FastAPI 应用入口
│   ├── collectors/              # 数据采集提供者
│   │   ├── __init__.py
│   │   ├── base.py              # 抽象基类（统一接口）
│   │   ├── westock.py           # WeStockProvider — westock-data-clawhub CLI
│   │   ├── sina.py              # SinaProvider — 行情 / K线 / 财务 / 资金流向
│   │   ├── neodata.py           # NeoDataProvider — 金融数据增强
│   │   └── rss.py               # RSSProvider — 通用 RSS 采集
│   ├── services/                # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── asset_service.py     # 追踪标的 CRUD
│   │   ├── evidence_builder.py  # 证据包组装（供 AI 消费）
│   │   ├── ai_analyzer.py       # AI 分析引擎
│   │   ├── news_service.py      # 新闻采集与关联
│   │   └── portfolio_service.py # 投资组合：账户、交易、持仓、盈亏
│   ├── storage/                 # 数据库层
│   │   ├── __init__.py
│   │   ├── database.py          # 连接管理
│   │   ├── schema.py            # 建表脚本（schema 唯一入口）
│   │   └── repository.py        # 通用 CRUD 仓库
│   ├── scheduler/               # 定时任务
│   │   ├── __init__.py
│   │   └── jobs.py              # APScheduler 任务注册
│   └── api/                     # FastAPI 路由
│       ├── __init__.py
│       ├── assets.py            # /assets 资源路由
│       ├── data.py              # /data 数据查询路由
│       ├── reports.py           # /reports AI 报告路由
│       ├── portfolio.py         # /accounts, /transactions, /positions 投资组合路由
│       └── tasks.py             # /tasks 任务管理路由
├── ui/                          # Streamlit 前端
│   ├── app.py                   # 主入口 + 页面路由
│   └── pages/                   # 各功能页面
├── data/                        # 数据文件（SQLite DB、日志）
│   └── marketlens.db
├── docs/                        # 项目文档
│   └── architecture.md
└── tests/                       # 测试（镜像 backend/ 目录结构）
    ├── collectors/
    ├── services/
    └── storage/
```

### 2.1 模块边界规则

- **`ui/`** 不直接读数据库，所有数据通过 FastAPI 接口获取
- **`backend/collectors/`** 是唯一可调外部数据源的模块
- **`backend/storage/`** 是唯一可执行 `CREATE TABLE` / `ALTER TABLE` 的模块
- **`backend/scheduler/`** 是唯一可注册定时任务的模块
- 新增数据源只在 `backend/collectors/` 下创建，遵循统一 Provider 接口

---

## 3. 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                      Streamlit UI                        │
│          (app.py + pages/)  ← 仅通过 HTTP API 通信        │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP (RESTful JSON)
┌──────────────────────────▼──────────────────────────────┐
│                   FastAPI 后端                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ /assets  │  │  /data   │  │ /reports │  │ /portfolio│ │ /tasks  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │              │              │      │
│  ┌────▼──────────────▼──────────────▼──────────────▼──┐ │
│  │                  services/                          │ │
│  │  AssetService  EvidenceBuilder  AIAnalyzer  PortfolioService │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │                  storage/                           │ │
│  │  Database  Schema  Repository (SQLite)              │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                           ▲
┌──────────────────────────┴──────────────────────────────┐
│              collectors/ (外部数据采集)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ WeStock  │ │  Sina    │ │ NeoData  │ │   RSS    │  │
│  │ Provider │ │ Provider │ │ Provider │ │ Provider │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │              │              │              │      │
│       ▼              ▼              ▼              ▼      │
│  [subprocess]   [HTTP GET]    [HTTP POST]   [HTTP GET]   │
└─────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              scheduler/ (APScheduler)                    │
│  行情 15min | 日收盘 16:00 | 新闻 60min | AI 20:00       │
│  每次任务 → run_logs (成功/失败/耗时/错误)                │
└─────────────────────────────────────────────────────────┘
```

### 3.1 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| **UI** | 渲染页面，调用 API，展示数据 | 不直接读 DB，不含业务逻辑 |
| **API 路由** | 参数校验，调用 service，返回 JSON | 不含业务逻辑 |
| **Services** | 业务逻辑编排，证据构建，AI 分析 | 不直接调外部数据源 |
| **Storage** | DB 连接、schema 管理、数据持久化 | 不含业务逻辑 |
| **Collectors** | 调外部数据源，原始→标准化转换 | 不写业务逻辑，不直接暴露给 UI |
| **Scheduler** | 定时触发采集&分析任务 | 不实现采集/分析逻辑本身 |

---

## 4. 数据流

### 4.1 采集流程

```
scheduler 触发 → AssetService.get_active_assets()
    → 遍历标的，路由到对应 Provider
    → Provider.search() / .quote() / .kline() / .finance() 等
    → 保存 raw_data (原始 JSON)
    → 标准化为 schema 字段 → 写入 DB
    → 写入 run_logs (task_name, status, started_at, finished_at, error_message)
    → 单个标的失败不影响后续标的
```

### 4.2 AI 分析流程

```
scheduler 或 API 触发 → EvidenceBuilder.build(symbol)
    → 从 DB 读取：行情、K 线、资金流、财务、新闻
    → 组装证据包（结构化 dict）
    → AIAnalyzer.analyze(evidence_package)
    → 规则引擎 / LLM 推理 → 输出固定 JSON schema
    → 写入 ai_reports 表
    → data_used 字段列出所有引用数据源
```

### 4.3 用户查询流程

```
UI 发起 GET /assets/{id}/report
    → API 路由 → 查询 ai_reports 表
    → 返回 JSON（含 action, confidence, reasons, data_used）
    → Streamlit 渲染卡片
```

---

## 5. 数据库 Schema

### 5.1 核心表清单

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `tracked_assets` | 用户追踪标的 | symbol, name, market, asset_type, enabled, tags |
| `market_quotes` | 实时行情快照 | symbol, price, change_pct, volume, timestamp |
| `kline_daily` | 日 K 线数据 | symbol, date, open, high, low, close, volume |
| `financial_reports` | 财务报表 | symbol, report_date, revenue, net_profit, eps, period |
| `fund_flows` | 资金流向 | symbol, date, main_inflow, main_outflow, net_flow |
| `technical_indicators` | 技术指标 | symbol, date, ma5, ma20, macd, rsi, boll_upper/lower |
| `news_items` | 新闻/公告/研报 | title, source, url, content, sentiment, importance, related_symbols |
| `ai_reports` | AI 分析报告 | symbol, action, confidence, risk_level, summary, reasons, data_used |
| `run_logs` | 任务运行记录 | task_name, status, started_at, finished_at, error_message, affected_assets |
| `raw_data` | 原始采集数据 | symbol, source, data_type, raw_json, collected_at |
| `accounts` | 交易账户 | name, broker, currency, notes |
| `transactions` | 交易记录 | account_id, symbol, type, quantity, price, fee, currency, trade_date |

### 5.2 投资组合相关表结构

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
| type | TEXT | NOT NULL | 交易类型 |
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

由 portfolio_service.py 实时聚合计算，不单独建表。计算逻辑：
- 聚合所有 deleted_at IS NULL 且 type IN (buy,sell,dividend,split) 的交易
- 按 (account_id, symbol) 分组
- 均价采用加权平均法（每次 buy 重新计算，sell/dividend/split 不改变均价）
- 实时从 market_quotes 获取最新价格以计算浮动盈亏



### 5.2 Schema 变更规则

- 所有 DDL 集中在 `backend/storage/schema.py`
- 禁止在业务代码中执行 `ALTER TABLE` 或 `CREATE TABLE`
- 新增表后同步更新本文档的核心表清单

---

## 6. 数据源架构

### 6.1 Provider 接口

所有 Provider 必须实现以下统一接口（在 `backend/collectors/base.py` 中定义为抽象基类）：

```python
class BaseProvider(ABC):
    @abstractmethod
    def search(self, keyword: str) -> list[dict]: ...
    @abstractmethod
    def quote(self, symbols: list[str]) -> list[dict]: ...
    @abstractmethod
    def kline(self, symbol: str, period: str = "daily") -> list[dict]: ...
    @abstractmethod
    def finance(self, symbol: str) -> dict: ...
    @abstractmethod
    def fund_flow(self, symbol: str) -> dict: ...
    @abstractmethod
    def technical(self, symbol: str) -> dict: ...
```

### 6.2 配置驱动的 Provider 实例化

`config.yaml` 中的 `data_sources` 顺序决定数据源优先级：

```yaml
data_sources:
  structured:
    - name: westock
      provider: WeStockProvider
      enabled: true
      timeout: 30
      params:
        command: "npx -y westock-data-clawhub@1.0.4"
```

代码中根据 `provider` 字段动态加载类，**不硬编码数据源名称或优先级**。

### 6.3 通用 Provider 复用

对于 HTTP GET 模式的源（如新浪财经、RSS），抽象为通用 `RSSProvider` 或 `HTTPProvider`，通过 `params` 注入 URL、headers 等差异，避免为每个源写重复代码。

### 6.4 容错规则

- 数据源失败 → 捕获异常 → `run_logs` 记录 → 继续下一个标的
- `optional: true` 的源不可用时静默跳过，不阻塞主流程
- 所有外部调用（subprocess、HTTP）必须设置超时（从 `config.yaml` 读取）

---

## 7. API 设计

遵循 RESTful 规范，使用 `restful-api-design` 技能进行设计评审。

### 7.1 资源路由总览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/assets` | 列表（支持 `?enabled=true&market=hk` 筛选） |
| `POST` | `/assets` | 添加追踪标的 |
| `GET` | `/assets/{id}` | 标的详情 |
| `PATCH` | `/assets/{id}` | 部分更新（启用/标签/备注） |
| `DELETE` | `/assets/{id}` | 删除追踪标的 |
| `POST` | `/assets/search` | 搜索标的（调用 Provider.search） |
| `GET` | `/data/quotes/{symbol}` | 最新行情 |
| `GET` | `/data/kline/{symbol}` | K 线数据（`?period=daily&limit=60`） |
| `GET` | `/data/finance/{symbol}` | 财务摘要 |
| `GET` | `/data/fund-flow/{symbol}` | 资金流向 |
| `GET` | `/news` | 新闻列表（`?symbol=&days=7`） |
| `GET` | `/reports` | AI 报告列表 |
| `GET` | `/reports/{symbol}` | 某标的最新/历史报告 |
| `POST` | `/reports/generate` | 手动触发 AI 分析 |
| `GET` | `/tasks/status` | 调度任务状态 |
| `POST` | `/tasks/trigger/{task_name}` | 手动触发采集任务 |

### 7.2 统一错误响应

```json
{
  "error": "ASSET_NOT_FOUND",
  "detail": "标的 'hk00700' 未找到"
}
```

HTTP 状态码：200 / 201 / 400 / 404 / 422 / 500

### 7.3 命名规范

- 资源名用小写连字符（kebab-case）：`fund-flow` 而非 `fund_flow`
- URL 使用名词复数：`/assets` 而非 `/asset`
- 查询参数用 snake_case（与 Python 惯例一致）

---

## 8. 调度系统

### 8.1 默认任务

| 任务 | 频率 | 说明 |
|---|---|---|
| `quote` | 每 15 分钟 | 采集所有活跃标的实时行情 |
| `daily_close` | 交易日 16:00 | 采集 K 线、资金流、技术指标 |
| `news` | 每 60 分钟 | 采集关联新闻 |
| `ai_report` | 每日 20:00 | 为所有标的生成 AI 分析报告 |

### 8.2 任务规范

- 所有定时任务通过 `APScheduler` 注册
- 每次执行写入 `run_logs`（`task_name`, `status`, `started_at`, `finished_at`, `error_message`, `affected_assets`）
- 任务必须幂等 — 重复执行不产生重复数据（通过 `INSERT OR IGNORE` 或去重逻辑保证）
- 支持通过 API 手动触发

---

## 9. AI 分析模块

### 9.1 证据驱动原则

```
禁止: AI 凭空输出"建议买入"
要求: AI 输出必须包含 data_used 字段，列出引用的数据源和采集时间
```

### 9.2 输出 Schema（不可擅自增删）

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

### 9.3 分析流水线

```
EvidenceBuilder.build(symbol)
  ├── 查 market_quotes → 当前价格、涨跌幅
  ├── 查 kline_daily → 近 60 日 K 线，计算 MA/MACD/RSI
  ├── 查 fund_flows → 近 5 日资金净流向
  ├── 查 financial_reports → 最新一期财报关键指标
  └── 查 news_items → 近 7 日关联新闻，情绪聚合
      ↓
  AIAnalyzer.analyze(evidence_package)
      ↓
  写入 ai_reports 表
```

第一版内置保守规则型分析器；后续可替换为真实 LLM 调用，接口不变。

---

## 10. 日志与可观测性

### 10.1 双轨日志

| 通道 | 工具 | 用途 |
|---|---|---|
| 本地文件日志 | `loguru` | 调试、开发阶段问题排查 |
| 数据库日志 | `run_logs` 表 | 运行期持久化追踪，UI 可查询展示 |

### 10.2 run_logs 表结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `task_name` | TEXT | 任务名称（quote / daily_close / news / ai_report） |
| `status` | TEXT | success / failure |
| `started_at` | TIMESTAMP | 任务开始时间 |
| `finished_at` | TIMESTAMP | 任务结束时间 |
| `error_message` | TEXT | 失败时的错误详情 |
| `affected_assets` | INTEGER | 受影响的标的数量 |

### 10.3 日志触发点

- 数据采集开始/结束/失败
- AI 分析开始/结束/失败
- 调度任务触发
- API 异常（通过 FastAPI 中间件统一捕获）

---

## 11. 配置管理

### 11.1 配置来源

所有可配参数集中于 `config.yaml`，代码启动时通过 `pyyaml` 加载为 dict。

### 11.2 配置分类

| 配置域 | key | 说明 |
|---|---|---|
| 数据源 | `data_sources.structured[]` | 结构化数据源列表（优先级 = 顺序） |
| 数据源 | `data_sources.news[]` | 新闻源列表 |
| 数据库 | `database.path` | SQLite 文件路径 |
| 数据库 | `database.echo` | SQL 日志开关 |
| 调度 | `scheduler.timezone` | 时区（Asia/Shanghai） |
| 调度 | `scheduler.tasks.*` | 各任务频率/CRON |
| AI | `ai.default_action` | 默认动作（证据不足时） |
| AI | `ai.confidence_threshold` | 置信度阈值 |

### 11.3 硬编码禁止清单

- ❌ 数据源名称/优先级
- ❌ 文件路径（DB、日志）
- ❌ 超时值
- ❌ API 密钥
- ❌ 调度频率

---

## 12. 错误处理策略

### 12.1 分层容错

```
数据源不可用 → 捕获异常 → run_logs 记录 → 跳过（不崩溃）
    ↓
单个标的采集失败 → 捕获异常 → run_logs 记录 → 继续下一个
    ↓
整个采集任务失败 → APScheduler 记录 → UI 显示任务状态异常
    ↓
FastAPI 异常 → 全局异常中间件 → 统一 JSON 错误响应
```

### 12.2 外部调用防护

- 所有 `subprocess.run()` 调用设置 `timeout` 参数
- 所有 `httpx` / `requests` 调用设置超时
- 超时值从 `config.yaml` 中对应源的 `timeout` 字段读取

---

## 13. 外部依赖

| 依赖 | 版本 | 用途 | 类型 |
|---|---|---|---|
| `westock-data-clawhub` | 1.0.4 | A 股/港股/美股结构化数据 | Node.js CLI（子进程调用） |
| 新浪财经 API | — | 行情 / K线 / 财务 / 资金流向 | HTTP 公开接口 |
| NeoData | — | 金融数据增强（可选） | HTTP API |
| RSS 源 | — | 财经新闻采集 | HTTP GET |

---

## 14. 部署与运行

### 14.1 环境要求

- Python ≥ 3.13
- Node.js ≥ v18
- `uv` 包管理器

### 14.2 启动命令

```bash
# 安装依赖
uv sync

# 启动 FastAPI 后端
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 启动 Streamlit UI
uv run streamlit run ui/app.py
```

### 14.3 单次运行

```bash
# 初始化数据库
uv run python -m backend.storage.schema

# 手动触发采集
curl -X POST http://localhost:8000/tasks/trigger/quote
```
