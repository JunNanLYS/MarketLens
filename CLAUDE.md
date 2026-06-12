# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

**MarketLens is a single-user, local-first tool.** It runs on the developer's own machine, talks to public financial data sources, and stores everything in a local SQLite file. There is no remote user base, no multi-tenant data, no internet-facing deployment.

When reviewing code or assessing risks, apply this **threat model**:

- ✅ **Real risks worth flagging** — data corruption, race conditions between concurrent API calls or scheduler ticks, timezone/locale bugs, misconfigured config, inconsistent docs, accessibility for the user, broken tests giving false confidence.
- ❌ **Not real risks — do NOT flag as "security vulnerabilities"**:
  - CSRF / cross-origin attacks — there's no remote attacker; the user's browser is the only client.
  - Phishing / XSS via ingested news or feed content — the user curates their own feeds; they are not attacking themselves.
  - "Publicly known" default API key (`marketlens-local`) — this is the user's local password, not a public secret. If `MARKETLENS_API_KEY` env var is unset, this default is the intended working value.
  - CORS `*` / wildcard in `config.yaml` — fine for a local tool, not a production deployment.
  - Timing attacks on `verify_api_key` — no remote attacker on the loopback interface.
  - Subprocess env var leakage to `npx` / CLI tools — the child process runs as the same user on the same machine.
  - "Hardcoded" secrets in `config.yaml` — these are local dev defaults, not production credentials.

If a finding only matters when the tool is exposed to untrusted networks or users, say so explicitly and do not block on it. Focus on correctness, performance, maintainability, testing, docs, and accessibility — these are the dimensions where this project can actually regress.

## Code review priorities

When reviewing this project (whether via `/code-review` skill, manual review, or any other means), spend time in this order. Do NOT default to the generic 7-dimension checklist (Security/Performance/Correctness/Maintainability/Testing/Accessibility/Documentation) — the Security leg is a false-positive generator here, and the dimensions are not equally important for a single-user financial tool.

### 1. Correctness — HIGHEST PRIORITY
Money math + time + concurrency bugs hit the user directly. Local tools have no remote shield, so defects surface as bad P&L or wrong AI reports.

- **Money math precision** — WAC, realized P&L, unrealized P&L, cross-account aggregation, split handling, multi-currency
- **Timezone & date handling** — every `datetime` must be `timezone.utc`; check trade_date type, range comparisons
- **Edge cases** — empty holdings, zero price, negative quantities (especially split `quantity > 0` write-time validation), `page=0`, `page_size=0`
- **Concurrency** — concurrent API calls can race with scheduler ticks; check-then-act in `update_transaction`/`delete_transaction`
- **Quote/position timing** — what happens if a tracked asset has no quote yet?

### 2. Data integrity & collection reliability
The project's core value is "evidence-driven AI." Every AI report depends on accurate collection. `raw_data` table is the audit trail.

- **Source failure isolation** — when one Provider throws, are others genuinely unaffected?
- **`optional: true` handling** — token missing / 401 → silent skip, not crash
- **Timeout config** — every external call (subprocess, HTTP) must have a `timeout` (CLAUDE.md hard constraint)
- **Idempotency** — scheduler re-runs must not duplicate rows; verify `INSERT OR IGNORE` / UNIQUE INDEX coverage
- **Schema evolution** — `ALTER TABLE` paths, column constraint migration
- **`raw_data` unbounded growth** — needs auto-cleanup

### 3. Performance — only the real bottlenecks
Already benchmarked: 100 assets < 2min, import 0.9s. Look for new regressions, don't relitigate solved ones.

- **N+1 queries** — especially portfolio's per-(account, symbol) aggregation
- **React component re-renders** — useMemo/useCallback for expensive computations in detail pages
- **Large fetch + Python-side aggregation** — `evidence_builder.build_multi` parses 5000 news rows in Python per batch
- **CTE pitfalls** — `get_asset_by_id` kline×flow Cartesian product risk
- **Write lock granularity** — currently locks the whole `_collect_*` method
- **Subprocess cold start** — westock `npx` 2-5s per call, 100 assets serialized

### 4. Maintainability
Single-user tool = you maintain it yourself. Code must be readable by you 3 months from now.

- **Config-driven vs hardcoded** — scattered `if symbol.startswith("sh")`?
- **Provider registry** — `base.py` 6 methods, are they `@abstractmethod` or empty stubs? (see Known issues)
- **Dead code** — unused methods, broken fixtures (`sample_asset` type cases)
- **Duplicated logic** — `collection_service.py` `_fetch_kline`/`_fetch_finance`/`_fetch_fund_flow`/`_fetch_technical` 4-way duplication
- **Type annotations + Chinese docstrings** — CLAUDE.md hard constraint

### 5. UI / accessibility / docs accuracy
You stare at the React 7-tab detail page daily. Color blindness, doc/code drift, dead UI options affect you.

- **P&L red/green only** — ~8% of male users can't distinguish; PnlDisplay uses ▲/▼ arrows as well
- **Cache TTL reasonableness** — quote 15min cycle, TanStack Query staleTime 30s reasonable
- **API doc/code sync** — `docs/api/*.md` vs `backend/api/*.py` field names, status codes
- **Emoji-only buttons** — ensure all icon-only buttons have `title` or `aria-label`
- **Dead UI options** — `running` filter that never matches

### 6. Integration & module boundaries
Strong module coupling is the local-tool tax. Cross-layer violations break deployment.

- **Layer boundaries** — does `ui/` import `backend/storage/` directly? (CLAUDE.md forbids)
- **Module boundaries per CLAUDE.md** — collectors, services, storage, scheduler isolation
- **Import time** — still < 1s? (lazy load intact?)
- **Resource cleanup** — `lifespan shutdown` closes all lazy clients

### Dimensions to NOT spend time on

| Skip | Why |
|------|-----|
| Generic Security checklist (CSRF, CORS, XSS, timing attacks, default-key exposure) | Single-user local tool — see "Project context" above |
| Multi-tenant / horizontal scaling | One user, one process, one SQLite |
| Performance load testing | Already benchmarked: 100 assets < 2min, import 0.9s |
| Production deployment concerns (TLS, auth providers, rate limits) | Not a deployed service |

## Commands

```bash
# Install dependencies
uv sync

# Run FastAPI backend (with auto-reload)
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Run React frontend (dev mode, proxy /api → backend)
cd frontend && npm run dev

# One-command launcher (backend + frontend dev, auto-open browser)
uv run python scripts/launcher.py

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/services/test_ai_analyzer.py -v

# Run a specific test
uv run pytest tests/services/test_ai_analyzer.py::test_analyze_bullish -v

# Run ruff code check (syntax, import, style, common bugs)
uv run ruff check .

# Auto-fix ruff issues
uv run ruff check --fix .

# Initialize/reset database
uv run python -m backend.storage.schema

# Manual trigger collection via API
curl -X POST http://localhost:8000/api/v1/tasks/trigger/quote

# Frontend commands (run from frontend/ directory)
cd frontend
npm run dev          # Vite dev server (port 5173, proxy /api → 8000)
npm run build        # Production build → frontend/dist/
npm run type-check   # TypeScript type checking (tsc --noEmit)
npm run lint         # ESLint check
npm test             # Vitest unit/integration tests
```

## Architecture

MarketLens is a **local-first, evidence-driven AI financial research assistant**. It tracks assets → auto-collects data → builds evidence packages → runs AI analysis → produces structured reports. All data stays in local SQLite.

### Layered design (top to bottom)

```
React + Vite UI (frontend/)  — display only; never touches DB directly, communicates via FastAPI API
FastAPI routes (api/)       — validate params, call services, return JSON
Services (services/)        — business logic orchestration
Collectors (collectors/)    — ONLY module that calls external data sources
Storage (storage/)          — ONLY module that runs CREATE TABLE / ALTER TABLE
Scheduler (scheduler/)      — ONLY module that registers APScheduler jobs
```

### Data source Provider pattern

`config.yaml` declares what sources exist, their priority order, and connection params. The `provider` field maps to a class name in `backend/collectors/`. Code dynamically loads providers by name — **never hardcode source names or priorities**.

All providers inherit from `BaseProvider` (defined in `collectors/base.py`) and must implement: `search()`, `quote()`, `kline()`, `finance()`, `fund_flow()`, `technical()`.

Failure isolation: a single source or asset failure is caught, logged to `run_logs`, and skipped — never crashes the system. Sources marked `optional: true` in config are silently skipped when unavailable.

### Evidence-driven AI pipeline

```
EvidenceBuilder.build(symbol)
  → reads from DB: quotes, K-lines, fund flows, financials, news
  → assembles a structured evidence dict (ONLY real collected data)
  → AIAnalyzer.analyze(evidence_package)
    → rule engine scores bullish/bearish signals by weighted dimensions
    → outputs fixed JSON schema with mandatory `data_used` field
    → stored in ai_reports table
```

AI output MUST include `data_used` listing every referenced data source and collection time — no hallucinated analysis.

### Dual logging

- **loguru**: local debug/file logging (never `print` or stdlib `logging`)
- **run_logs table**: persistent runtime tracking with `task_name`, `status`, `started_at`, `finished_at`, `error_message`, `affected_assets`. UI can query task execution history.

### Database

SQLite only (no other DB). WAL mode + foreign keys ON. Both sync (`sqlite3`) and async (`aiosqlite`) connection helpers in `storage/database.py` via context managers (`get_db` / `aget_db`). Tests use `init_db_sync()` for fixture setup.

All DDL lives in `storage/schema.py` — never run `CREATE TABLE` or `ALTER TABLE` in business code. New tables must be added to both `TABLE_DDLS` and the core table list in `docs/architecture.md`.

### Scheduler

APScheduler (`scheduler/jobs.py`) runs 4 tasks: `quote` (15min), `daily_close` (weekdays 16:00), `news` (60min), `ai_report` (daily 20:00). Each task is idempotent (uses `INSERT OR IGNORE` / dedup). Tasks can be manually triggered via `POST /api/v1/tasks/trigger/{name}`.

### Portfolio system

Positions are computed in real-time (not persisted). `portfolio_service.py` aggregates transactions by (account_id, symbol), uses weighted-average cost, fetches latest quotes for market value, and calculates unrealized/realized P&L. Soft delete (`deleted_at` timestamp) on accounts and transactions preserves audit trail.

## Key constraints

- **所有 PR 必过 GitHub Actions CI（ruff + pytest）**：见 `.github/workflows/ci.yml`，`push` 到 `main` 与 `pull_request` 触发两个 job——`ruff` 跑 `uv run ruff check .`，`pytest` 在 Python 3.13 matrix 下跑 `uv sync --frozen` + `uv run pytest tests/ -v`。
- **Python ≥ 3.13** with `uv` package manager; use `.venv`, never system Python
- **Node.js ≥ v18** required for `westock-data-clawhub` CLI (WeStock data source)
- All comments and docstrings in **Chinese**
- **Encoding**: 所有源文件必须使用 **UTF-8 无 BOM** 编码。CI runner / pre-commit hook / formatter 保存文件时不得改变编码。文件头部不要加 `#!/usr/bin/env python` 或编码声明（Python 3 默认 UTF-8）。
- Import order: stdlib → third-party → local
- Type annotations required on all function signatures and class attributes
- All configuration reads from `config.yaml` (paths, timeouts, keys, schedules)
- API: all routes under `/api/v1/`; `GET` has no side effects; errors return `{"error": "...", "detail": "..."}`
- Tests mirror `backend/` directory structure; `pytest` with `asyncio_mode = "auto"`
- Data processing prefers `pandas`; file paths use `pathlib`; PEP8 compliance
- Every collection must persist **both raw response and normalized data** (audit-traceability)

### Module boundaries (enforced)

```
backend/collectors/  → ONLY module that calls external data sources
backend/services/    → business logic orchestration (track assets, build evidence)
backend/storage/     → database read/write + init schema
backend/scheduler/   → ONLY module that registers APScheduler jobs
backend/main.py      → FastAPI entry: route registration, middleware, exception handlers
frontend/            → React + Vite UI; NEVER touches DB directly, must go through FastAPI
tests/               → must mirror backend/ directory structure
docs/                → project documentation (PRD, architecture, API docs)
```

### Async / concurrency hard constraints

- All `Service` and `Provider` methods **MUST** be `async def`; blocking sync IO (subprocess, file IO, CPU-bound work) must be wrapped with `asyncio.to_thread` to avoid blocking the event loop.
- **Provider httpx client lazy-load**: `__init__` MUST NOT create an `httpx.AsyncClient`. The client is created on first `await` to avoid ~3.8s blocking × 10 Providers = ~38s import-time stall on Windows + Python 3.13.
- **SQLite write serialization**: the sync `sqlite3` connection does NOT support concurrent writes from multiple coroutines. All write paths MUST hold a module-level `asyncio.Lock`; reads may proceed concurrently.
- **APScheduler `_run_*` wrapper layer**: APScheduler's scheduler thread calls a sync wrapper (e.g. `_run_quote`) that internally does `asyncio.run(async_business(...))`. When testing the underlying async business, mock `asyncio.run` to inject a probe — do not re-invoke the wrapper.
- **External calls** (subprocess, HTTP) MUST set a timeout and catch exceptions; a single source/asset failure must never crash the system.

### Test conventions

- `asyncio_mode = "auto"` in `pyproject.toml` — all `test_*` functions MUST be `async def`.
- Mocking a Provider's HTTP layer: assign `provider._client = AsyncMock()` to **skip the lazy-load path** and inject a deterministic response; do not mock `httpx.AsyncClient` constructor.
- Test fixtures use `init_db_sync()` from `storage/database.py` to set up an isolated SQLite database.

### Scheduler task contract

Every APScheduler job MUST:
1. Declare a fixed frequency (default cadences: `quote` 15min, `daily_close` / `kline` / `fund_flow` / `technical` on weekday close, `news` 60min, `ai_report` nightly).
2. Be **idempotent** — re-runs MUST NOT produce duplicate rows (use `INSERT OR IGNORE` / dedup keys).
3. Write a `run_logs` row covering `task_name` / `status` / `started_at` / `finished_at` / `error_message` / `affected_assets`.

### API design hard rules

> Use the `restful-api-design` skill when designing or reviewing endpoints.

- `GET` MUST NOT have side effects (no `?force=true` triggering writes). Forced refresh lives in a separate `POST .../refresh` endpoint.
- `POST` MUST NOT be used for pure queries (e.g. search) — use `GET` with query parameters.
- `DELETE` returns `204 No Content` on success with no body.
- All endpoints live under `/api/v1/`; error responses are uniformly `{"error": "...", "detail": "..."}`.

### Logging & observability

- `loguru` is the only logger (no `print`, no stdlib `logging`) — handles local debug + file logging.
- The `run_logs` table is the persistent runtime ledger: `task_name` / `status` / `started_at` / `finished_at` / `error_message` / `affected_assets`. The UI queries this for task history.
- Data collection, AI analysis, and scheduler triggers MUST all leave a `run_logs` row.

## Skills

> When working on this project, invoke the following skills as appropriate:

| Skill | When to use |
|---|---|
| `code-review` | Review code changes for bugs, simplifications, and efficiency |
| `fastapi-backend-tester` | Write and run FastAPI backend tests |
| `fastapi-pro-expert` | FastAPI best practices (Pydantic v2, DI, async DB, auto-docs) |
| `skill-fastapi` | FastAPI + SQLModel coding conventions (project structure, routing, services, testing) |
| `restful-api-design` | RESTful API design standards |
| `git-commit` | Conventional commit messages with intelligent staging |
| `verify` | Verify changes work by running the app |

## Known issues

See `ISSUES.md` for a comprehensive audit covering correctness, performance, and maintainability findings.

下方 4 条 **截至 2026-06-06 已通过代码验证实际解决**，保留以追踪决策历史；新增问题请追加到本节末尾。

- ✅ ~~`BaseProvider` defines 6 abstract methods but news/RSS providers only implement `search()` — the rest return empty stubs~~ → 拆分为 `StructuredProvider` + `NewsProvider` 两个 ABC（[base.py:22,71,102](backend/collectors/base.py)）；新闻类 Provider 改为继承 `NewsProvider` 并删去 6 个空 stub；MRO 兼容性由 [test_base_abcs.py](tests/collectors/test_base_abcs.py) 11 个单测守护。
- ✅ ~~`ai_reports` table uses an index rather than a UNIQUE constraint on `(symbol, date(generated_at))`, risking duplicate reports~~ → 已升级为 `CREATE UNIQUE INDEX`（[schema.py:271-272](backend/storage/schema.py)）。
- ✅ ~~`raw_data` table has no auto-cleanup and will grow unbounded~~ → `cleanup` 定时任务每天 03:30 删除 `>30 days` 记录（[jobs.py:195-213](backend/scheduler/jobs.py)）。
- ✅ ~~`Service instances are recreated per scheduler tick rather than cached~~ → `_collection_service` / `_news_service` 已为模块级懒加载单例（[jobs.py:145-158](backend/scheduler/jobs.py)），APScheduler 每次 tick 复用同一实例。
- ✅ ~~`SentimentResult.to_db_value()` 默认阈值 0.4 过低导致 0.4~0.55 区间的"擦边球"被保留为正/负面~~ → 已提至 0.55（[models.py:36](backend/services/sentiment/models.py)），并配套 `news_items` 扩 `confidence` + `sentiment_reason` 两列落库原始评分；`evidence_builder` 新增 `_aggregate_news` 输出 weighted sum 与 sector_exposure，让高置信新闻的"情绪强度"进入 AI 证据包。

### External dependencies (fact, not bugs)

- `NeoDataProvider` 的 token 由**外部 workbuddy 工具**写入 `~/.workbuddy/.neodata_token`，
  本项目不参与申请/刷新。`optional: true` 保证 token 缺失或 401 时静默降级，
  不会阻塞其他数据源。详见 `backend/collectors/neodata_client.py::TokenManager`。
  若需 UI 提示用户"该去 workbuddy 刷新 token",使用 `GET /api/v1/data-sources/status` 的 `neodata` 字段。

## Task Completion Checklist

After **every** task, execute these steps in order:

### 1. Error Check

Scan all modified files for syntax errors or statically detectable logic issues. If errors are found, fix them and **restart from step 1**.

### 1.5 Ruff Check

Run ruff on all modified `.py` files:
```bash
uv run ruff check .
```
If issues are found, fix them and re-run until clean.

### 1.75 Frontend Check

当 `frontend/` 目录下任何文件被修改时,运行前端静态检查(全通过才视为"前端无误"):

```bash
cd frontend
npm run lint
npm run type-check
npm run build
```

任一命令失败 → 修复后**重新从 step 1 开始**。

> 命令来源:`frontend/package.json` scripts。`type-check` 是带连字符的正式名(`tsc -b --noEmit`),不是 `typecheck`;`build` 内嵌 `tsc -b && vite build`,虽与 `type-check` 语义重叠,但单独跑 `type-check` 失败暴露更快、定位更准。Vitest 单元/集成测试归到 step 2。

### 2. Test Judgment & Execution

Determine if the task falls into test-required categories:
- New or modified business logic in `backend/`
- New or modified API endpoints (routes, services)
- Database schema or storage layer changes

If so, run relevant tests (`uv run pytest tests/` or specific test files). Ensure **all tests pass** before proceeding.

### 3. Documentation Sync

When APIs are added, modified, or removed:
- Update the corresponding docs in `docs/api/`
- Check if `docs/prd.md`, `docs/features.md`, `docs/architecture.md` need cascading updates

### 4. Git Commit & Push

Commit all changes with a conventional commit message (use `git-commit` skill):
- **Title**: one-line summary of the change (e.g. `feat: add portfolio P&L chart`)
- **Body**: detailed breakdown by functional module
- After commit, push to remote if configured.

## Project state

> 本章节为新会话接手时的"项目当前快照"，避免重复探索已知的项目结构、规模、修复历史。事实型数据已对照代码与 `ISSUES.md` 校准（2026-06-08）。

### 当前规模

- **29 张表**（SQLite，DDL 全在 `backend/storage/schema.py::TABLE_DDLS`）
- **74 端点**（68 在 `backend/api/*.py` + 2 在 `backend/main.py` 健康/根 + 4 `data_sources` 子路径，全部 `/api/v1/` 前缀）
- **8 个 Provider**（`backend/collectors/*.py`：NeoData / RSS / SearchEngineNews / Sina / SinaNews / TencentNews / TencentNewsHTTP / WeStock）
- **458 测试**（`tests/`，`pytest asyncio_mode = "auto"`）
- **React + Vite 前端**（`frontend/`，7 页面全部迁移完成：Settings / NewsList / TaskStatus / AiReports / TrackedAssets / Portfolio / AssetDetail）

### 资金主线 CRITICAL 状态

**8 / 8 已修**（资金 5 + 写锁 3），逐条复验见 `ISSUES.md` 第 8 轮复验记录（2026-06-07）：

- 资金主线 5 条：`portfolio_service` 的 `update_transaction` 写锁 / `delete_transaction` 写锁 / split 校验 / WAC 幻股 / WAC fee
- 写锁 3 条：`news_service` 写锁 / `_run_cleanup` 写锁 / 第 6 轮补登 `report_service.generate_reports` 写锁

项目当前已无资金/写锁类 P0 阻断性 bug。

### 基础设施

- **CI** — `.github/workflows/ci.yml`：`push` 到 `main` 与 `pull_request` 触发两个 job
  - `ruff`：`uv run ruff check .`
  - `pytest`：Python 3.13 matrix，`uv sync --frozen` + `uv run pytest tests/ -v`
- **pre-commit** — `.pre-commit-config.yaml`，钩子分三档：
  - 文件卫生（`trailing-whitespace` / `end-of-file-fixer` / `check-yaml` / `check-toml`）
  - ruff lint + format（锁定 `ruff>=0.15.16`）
  - pytest fast（`pre-push` 阶段，`-x` 遇首个失败即停）
- 安装命令：`uv run pre-commit install --hook-type pre-commit --hook-type pre-push`

### 8 轮修复历史摘要

- **第 4-7 轮审查** — 4-Agent 并行深度复审，发现 70+ 条（CRITICAL 8 / MAJOR 12 / MINOR 19 / NIT 10 = 48 登记条目，外加 5 轮 26 条附加项）
- **第 8 轮** — 资金主线 8 个 CRITICAL 全部修复 + 复验记录入库
- **第 9 轮** — 5 条收尾（quotes CTE MAJOR / naive datetime MAJOR / realized-pnl 翻页 doc MINOR / lifespan 资源清理 NIT / westock 贪婪匹配 NIT）
- **第 10 轮** — 7 doc 校准 + 30 个 client 方法补全（72 端点全覆盖）+ realized-pnl wrapper 同构
- **第 11 轮** — 收尾：`git mv` 清理错位文件 / pre-commit 钩子补全 / CI workflow 落地
- **第 12 轮** — Streamlit → React + Vite 完整迁移：7 页面全部实现 / Streamlit 删除 / 启动器重构 / CI 增加 frontend job / 文档同步

> 详细逐条复验表 + 决策追踪见 `ISSUES.md` 第 8-11 轮复验记录（行 117-200）。

### 关键设计决策（经验沉淀）

CLAUDE.md 已有 "Architecture" 段描述分层与 Provider 模式；以下是 **实操经验**（不在任何其他文档，复用时务必遵守）：

1. **`_WRITE_LOCK` 必须包裹所有 SQLite 写路径**（CLAUDE.md 硬约束，第 209-213 行）
   - 同步 `sqlite3` 不支持多协程并发写；所有写路径必须 `with _WRITE_LOCK:`，读路径可并发
   - 历史教训：第 4 轮 5 个 portfolio 写端点全部漏锁 → 用户 P&L 串号；第 6/8 轮补登 `report_service` / `news_service` / `_run_cleanup` 3 处
   - 新增 Service / 新增写端点 → 第一件事就是加 `with _WRITE_LOCK:`

2. **`frontend/` 严禁 import `backend/storage/`**（Module boundaries，第 197-207 行）
   - UI 必须走 FastAPI（`frontend/src/api/client.ts`），绝不能直接碰 SQLite
   - 跨层 import 是部署期地雷：UI 与 backend 用不同的 venv/进程时会立即炸

3. **文档同步 = 后端代码改必动 `docs/api/*.md`**（Task Completion Checklist 第 3 步）
   - 端点签名、状态码、字段名 3 处任一变动 → 同步更新 `docs/api/*.md`
   - 过去教训：第 4-7 轮发现 30+ 处 doc/code drift；第 10 轮 Agent 3 专门 7 doc 校准 + 30+ 处状态码修正

4. **evidence-driven AI：每条采集数据必须被 `_check_*` 消费**（Architecture 第 149-161 行）
   - `EvidenceBuilder.build(symbol)` 只组装**真实采集**的证据；AI 输出必须含 `data_used` 字段列出每个引用源 + 采集时间
   - 不允许 hallucinate 分析；这条是项目"证据驱动"价值主张的底线

## Issue tracker 迁移（CODE_REVIEW.md → ISSUES.md）

> **新会话接手时务必知道的"文件重命名"事实**，避免误以为仓库里没有 issue tracker。

**事实**：
- **2026-06-08（第 11 轮）**：`git mv CODE_REVIEW.md ISSUES.md`
- 决策依据：10 轮审查+修复后，`CODE_REVIEW.md` 主体已无活跃问题登记（仅保留决策历史/复验记录），文件名"Code Review"暗示"审查动作"已与实际角色（issue tracker + 决策归档）不匹配
- `git mv` 保留完整 history 审计追踪链（rename 79% 匹配）

**当前 `ISSUES.md` 角色**（**根目录 active tracker**）：
- 发现新 bug → 在根 `ISSUES.md` **"已知问题登记"**章节追加条目
- 修复后从根 `ISSUES.md` 删除该条目
- **项目状态稳定后（主体清零）** → `git mv` 整个 `ISSUES.md` 到 `docs/dev/issues_<归档日期>.md` → 在根创建新空 `ISSUES.md` 模板
- 这样根 `ISSUES.md` 永远反映"当前活跃问题"，归档文件保留决策历史
- `docs/dev/issues_2026-06-08.md` —— 第 4-11 轮审查 70+ 条 + 9 轮修复决策历史（首次归档）

**所有引用迁移完成**（11 轮一次性同步）：
- `CLAUDE.md` line 261（"Known issues" 章节曾引导到 `See ISSUES.md`——第 10 轮删除 Known issues 章节时此引导句仍保留；第 11 轮 git mv 时已同步引用）
- `docs/architecture.md` 4 处
- `ui/app.py` 1 处注释
- `ui/pages/portfolio.py` 1 处 docstring
- `tests/collectors/test_sina.py` 1 处测试注释

**禁止行为**：
- 不要 `git rm ISSUES.md` + `git add docs/dev/issues_*.md`（会断 history，应 `git mv`）
- 不要新建 `CODE_REVIEW.md` 文件（git history 已保留）
- 不要在 git commit message 中用 `CODE_REVIEW.md`（用 `ISSUES.md`）
- 不要在 `docs/dev/issues_*.md` 文件**追加**新内容（归档文件只读，新内容去根 `ISSUES.md`）

## 经验速查（lessons_learned.md）

> **新会话接手第 1 件事**：扫读 [`docs/dev/lessons_learned.md`](docs/dev/lessons_learned.md)（5 分钟速查版）
>
> 该文件集中归档了 4-12 轮审查/修复中所有"踩过的坑"与"实操最佳实践"，
> 避免散落在 CLAUDE.md / ISSUES.md / 归档文件各处反复探索。
>
> **覆盖主题**：
> 1. `_WRITE_LOCK` 写锁包裹所有 SQLite 写路径（含 4 轮历史教训）
> 2. `ui/` 严禁 import `backend/storage/`
> 3. 改后端必动 `docs/api/*.md`
> 4. evidence-driven AI：`_check_*` 必须与 symbol 强相关
> 5. `Provider.close()` MRO 陷阱（含 `_HttpClientMixin` 叶子节点说明）
> 6. 锁测试 `_ObservableLock` 范式 + 双向 patch
> 7. loguru `caplog` 桥接缺失 → 用 `logger.add(lambda)`
> 8. sync 改 async 时旧测试 `RuntimeWarning`
> 9. 多 Agent 文件零交叉可完全并行
> 10. 静默 `LIMIT` 必须截断探测

**与本文件关系**：
- **CLAUDE.md** —— 项目硬约束、架构、命令（必读）
- **lessons_learned.md** —— 历次踩坑 + 实操经验（必读）
- **ISSUES.md** —— 当前活跃 issue tracker（修完即删）
- **docs/dev/issues_*.md** —— 历史归档（只读）

