# MarketLens

> 本地优先、证据驱动的 AI 金融研究助理 — 追踪标的 → 自动采集数据 → 证据包 → AI 分析 → 结构化报告。

MarketLens 是一款单用户、本地运行的金融研究工具。它在开发者的本机调度公开数据源（新浪 / 腾讯 / WeStock / RSS / NeoData），将行情、财报、资金流、新闻、ETF、板块等数据持久化到本地 SQLite，再以"证据包 + 规则评分"方式产出 AI 分析报告，全部用于自己的 A 股 / 港股 / 美股研究。

不做多租户、不上云、不联网。代码就是产品，数据就是资产。

---

## 技术栈

| 维度 | 选型 |
|---|---|
| 语言 | Python ≥ 3.13 |
| 包管理 | `uv`（`.venv` 隔离，不用系统 Python） |
| 后端 | FastAPI + Pydantic v2（异步路由） |
| 前端 | React + Vite + TypeScript（Ant Design 5） |
| 数据库 | SQLite（WAL + `foreign_keys=ON`），同步 `sqlite3` + 异步 `aiosqlite` 双连接 |
| 调度 | APScheduler `BackgroundScheduler` |
| HTTP | `httpx.AsyncClient`（Provider 懒加载） |
| 数据源 CLI | Node.js ≥ v18（仅 `westock` 数据源启用时必需） |
| 日志 | loguru（文件）+ `run_logs` 表（持久化） |
| 测试 | pytest + pytest-asyncio（`asyncio_mode="auto"`） |
| Lint | ruff |

---

## 数据流概览

```
                +----------------------+
                |  React + Vite UI (frontend/)  |   仅通过 HTTP 通信，不直连 DB
                +----------+-----------+
                           |  HTTP /api/v1/* (JSON)
                +----------v-----------+
                |   FastAPI (api/)     |   鉴权 + 参数校验 + 路由分发
                +----------+-----------+
                           |
                +----------v-----------+
                |  Services (services/) |  业务编排（全部 async）
                |  CollectionService    |  → asyncio.gather + Semaphore(10)
                |  EvidenceBuilder      |  → DB → 结构化证据包
                |  AIAnalyzer           |  → 规则评分 → JSON schema (data_used 必填)
                |  PortfolioService     |  → WAC + 实时市值
                +----+-----------+------+
                     |           |
        +------------v--+   +----v---------+
        | Storage (storage/) | Collectors  |  唯一可调外部数据源的层
        | get_db/aget_db     |  (collectors/) |  8 个 Provider 懒加载
        | schema (29 张表)   +-----+--------+
        +-------------------+       |
                                    | subprocess / HTTP
                            +-------v--------+
                            |  外部数据源      |
                            |  westock sina   |
                            |  rss tencent    |
                            |  neodata        |
                            +----------------+

                +----------------------+
                |  Scheduler (APSched) |  quote 15min | daily_close 16:00
                |  5 个定时任务          |  news 60min | ai_report 20:00
                +----------------------+  cleanup 03:30
```

### 关键设计

- **本地优先** — DB、日志、调度、AI 分析全在本地，无云依赖
- **证据驱动** — AI 输出强制带 `data_used` 字段列出真实数据源，杜绝凭空分析
- **源失败隔离** — Provider / 标的单点失败不阻塞整体流程
- **配置驱动** — `config.yaml` 声明数据源与参数，代码不硬编码源名 / 优先级
- **懒加载 HTTP 客户端** — `__init__` 不创建 `httpx.AsyncClient`，首次 await 时再建，10 个 Provider 累加 import time 从 ~38s 降至 0.9s
- **SQLite 写串行化** — `threading.Lock` 跨协程保护所有 `INSERT/DELETE`；读无锁

---

## 当前规模（截至 2026-06-07，第 9 轮审查后）

| 维度 | 数量 | 说明 |
|---|---|---|
| 数据库表 | **29 张** | 28 张业务表 + `raw_data`（含 raw_json 审计），全部由 `backend/storage/schema.py::TABLE_DDLS` 统一管理 |
| API 端点 | **74 个** | 业务 72 + 系统 2（`/`、`/api/v1/health`），全部位于 `/api/v1/` 前缀下 |
| 数据源 Provider | **8 个** | `WeStockProvider` / `SinaProvider` / `SinaNewsProvider` / `TencentNewsProvider` / `TencentNewsHTTPProvider` / `RSSProvider` / `SearchEngineNewsProvider` / `NeoDataProvider` |
| 调度任务 | **5 个** | `quote` / `daily_close` / `news` / `ai_report` / `cleanup` |
| 测试 | **457 个** | pytest-asyncio 全量通过；镜像 `backend/` 目录结构 |
| AI 端点 | **4 个** | 报告列表 / 单标最新 / 历史 / 手动生成 |
| 投资组合端点 | **12 个** | 账户 CRUD（5）+ 交易 CRUD（5）+ 持仓总览（1）+ 已实现盈亏（1） |
| 鉴权端点 | **26 个** | 写端点全部要求 `X-API-Key` 头，默认 key `marketlens-local`（仅本地） |
| 前端 | **7 页面** | React + Vite + TypeScript + Ant Design 5（Settings/NewsList/TaskStatus/AiReports/TrackedAssets/Portfolio/AssetDetail） |

---

## 快速开始

```bash
# 1. 安装依赖（uv 会自动创建 .venv）
uv sync

# 2. 初始化数据库（首次运行或 schema 变更后）
uv run python -m backend.storage.schema

# 3. 启动 FastAPI 后端（开发模式，含自动重载）
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 4. 启动前端（开发模式，Vite 代理 /api → FastAPI）
cd frontend && npm run dev

# 或使用统一启动器（dev: Vite 子进程 + uvicorn; prod: 单端口）
uv run python scripts/launcher.py
```

启动后访问：

- 后端 Swagger UI — http://localhost:8000/docs
- 后端健康检查 — http://localhost:8000/api/v1/health
- React UI（开发）— http://localhost:5173
- React UI（生产）— http://127.0.0.1:8000

### 手动触发采集

```bash
# 触发实时行情采集（写端点需 X-API-Key）
curl -X POST http://localhost:8000/api/v1/tasks/trigger/quote \
  -H "X-API-Key: marketlens-local"
```

### 运行测试

```bash
# 全部测试
uv run pytest tests/ -v

# 单文件
uv run pytest tests/services/test_ai_analyzer.py -v

# 单个用例
uv run pytest tests/services/test_ai_analyzer.py::test_analyze_bullish -v
```

### Lint

```bash
uv run ruff check .
uv run ruff check --fix .   # 自动修复
```

---

## 项目结构

```
MarketLens/
├── config.yaml               # 全局配置（数据源、调度、AI 阈值、安全）
├── pyproject.toml            # 依赖与元数据（uv 管理）
├── CLAUDE.md                 # 项目开发规范与硬约束
├── backend/
│   ├── main.py               # FastAPI 入口 + SecurityHeadersMiddleware
│   ├── api/                  # 8 个资源组路由（assets/data/news/...）
│   ├── collectors/           # 8 个 Provider，唯一可调外部数据源
│   ├── services/             # 业务编排（CollectionService/EvidenceBuilder/AIAnalyzer/...）
│   ├── storage/              # schema.py (29 张表) + database.py (连接管理)
│   └── scheduler/            # APScheduler 任务注册与异步包装
├── frontend/                 # React + Vite 前端
├── data/                     # SQLite DB + loguru 日志
├── docs/                     # architecture.md + api.md + api/*.md
└── tests/                    # 457 个测试，镜像 backend/ 结构
```

完整架构与分层职责见 [`docs/architecture.md`](docs/architecture.md)；74 个端点速查见 [`docs/api.md`](docs/api.md)。

---

## 第 12 轮：React 迁移完成

项目已完成 9 轮系统性代码审查，修复 **65+ 条问题**，覆盖以下主线：

### 资金主线（CRITICAL 全部已修）

第 5 轮 ~ 第 9 轮针对投资组合（账户 / 交易 / 持仓 / 已实现盈亏）累计修复 8 条 CRITICAL：

- 加权平均成本（WAC）在 `split` 交易时按比例下调，不污染均价
- 卖出校验当前持仓充足（`INSUFFICIENT_HOLDING` 400）
- 已实现盈亏按 FIFO / 移动平均法精确计算，跨账户聚合不丢失
- 多币种账户隔离，币种转换不串值
- 软删除（`deleted_at`）保持审计可追溯
- 写端点全部走 `verify_api_key` 依赖，杜绝未授权写入
- `realized-pnl` 页面与 `/transactions` 同构，避免前端误读
- `frontend/src/api/client.ts` 30 个 client 方法补全（72 端点全覆盖）

### 文档校准

- `docs/api.md` 校准 7 篇子文档、30+ 处状态码修正
- `docs/api/*.md` 子文档与 `backend/api/*.py` 字段名 / 状态码完全同步
- `docs/architecture.md` 表数（29 张）、端点分布、调度清单与代码一致

### 已知问题清单

详见 [CLAUDE.md](CLAUDE.md) "Known issues" 章节。下方 4 条截至 2026-06-06 已通过代码验证实际解决：

- `BaseProvider` 拆分为 `StructuredProvider` + `NewsProvider` 双 ABC（[base.py:22,71,102](backend/collectors/base.py)）
- `ai_reports` 升级为 `CREATE UNIQUE INDEX` 防止同日重复（[schema.py:271-272](backend/storage/schema.py)）
- `raw_data` 接入 `cleanup` 定时任务，30 天前自动删除（[jobs.py:195-213](backend/scheduler/jobs.py)）
- `_collection_service` / `_news_service` 改为模块级懒加载单例（[jobs.py:145-158](backend/scheduler/jobs.py)）

---

## 开发约定（与 CLAUDE.md 一致）

- 所有注释 / docstring 用**中文**
- 函数签名必须有类型注解
- 业务代码不执行 `CREATE TABLE` / `ALTER TABLE`（统一在 `schema.py`）
- 写端点必须有 `X-API-Key` 鉴权依赖
- 所有外部调用（subprocess / HTTP）必须设 `timeout`
- 任何修改后执行 `uv run ruff check .` 与 `uv run pytest tests/`

---

## 许可

单用户本地工具，未指定开源许可。
