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

见下方 [Module boundaries (enforced)](#module-boundaries-enforced)。

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

### Configuration discipline — no hardcoded tunables

任何**用户可调**的值(超时、阈值、间隔、路径、限制、cron、市场前缀、清理规则、API 端点、retry 次数等)必须声明在 `config.yaml`;在代码里硬编码这些值 = bug。改 YAML 必须下次读取生效,不应需要重启/编译。

**Why:** 单用户本地工具,自己维护自己改;硬编码默默破坏 "config-driven" 承诺(2026-06-08 审计一次抓出 6+ 处:`markets` 前缀字面量散落、证据包 `60`/`5` 限制、token 24h 禁用、清理规则表写死、`cleanup.retention` 段缺失等)。审查时 **Config-driven vs hardcoded** 是 Maintainability 第一条;本节把它升级为硬约束。

**How to apply:**
- 引入任何可调值 → **先**在 `config.yaml` 加字段,代码用 `get_config()` / `ConfigStore` 读取。
- YAML 缺失/类型错误 → 用 `_FALLBACK_*` 常量兜底 + `logger.warning(...)`,**不**静默用魔法值(已建立的模式见 `evidence_builder.py` / `asset_service.py` / `scheduler/jobs.py`)。
- **不适用本规则**(代码层不变量,非用户可调):hash 桶大小、retry 指数、正则字符类内部细节;以及"用户愿意改源码"的一次性常量(如 `_CLEAR_CACHE_DISABLE_SECONDS = 30` —— token 锁定时长,2026-06-13 通过源码编辑 3 次而非 YAML)。判断标准:**用户会想改它吗?会 → 进 config;不会 → 代码常量。**
- 新增 config 字段:同步 `docs/api/*.md`(如有 API 暴露)+ Settings 页面(如有 UI 暴露)+ commit message。
- code review 时,凡看到裸 `re.compile(r"^(sh|sz|hk|...)"\\w+)$` / `if x > 60` / `time.sleep(24*3600)` 这类"看起来能改"的常量,必须问"为啥不放 config.yaml?"。

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

Claude Code 自动从可用 skills 列表加载,无需在此登记。需要时调用即可。

## Known issues

See `ISSUES.md` for the comprehensive audit covering correctness, performance, and maintainability findings.

下方 5 条 **截至 2026-06-06 已通过代码验证实际解决**，保留以追踪决策历史；新增问题请追加到本节末尾。

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

**8 / 8 已修**（资金 5 + 写锁 3），逐条复验见 `ISSUES.md` 第 8 轮复验记录（2026-06-07）。项目当前已无资金/写锁类 P0 阻断性 bug。

### 基础设施

- **CI** — `.github/workflows/ci.yml`：`push` 到 `main` 与 `pull_request` 触发两个 job
  - `ruff`：`uv run ruff check .`
  - `pytest`：Python 3.13 matrix，`uv sync --frozen` + `uv run pytest tests/ -v`
- **pre-commit** — `.pre-commit-config.yaml`，钩子分三档：
  - 文件卫生（`trailing-whitespace` / `end-of-file-fixer` / `check-yaml` / `check-toml`）
  - ruff lint + format（锁定 `ruff>=0.15.16`）
  - pytest fast（`pre-push` 阶段，`-x` 遇首个失败即停）
- 安装命令：`uv run pre-commit install --hook-type pre-commit --hook-type pre-push`

### 配套文档（按需扫读）

- **[`docs/dev/lessons_learned.md`](docs/dev/lessons_learned.md)** — 11 项实操经验(写锁/分层/文档同步/evidence/Provider MRO/锁测试/loguru/sync→async/多 Agent/截断探测/依赖声明)。**新会话第 1 件必读。**
- **`ISSUES.md`** — 当前活跃问题登记(修完即删)。
- **`docs/dev/issues_*.md`** — 历史归档(只读,记录 4-12 轮 70+ 条审查+修复决策)。第 11 轮 `git mv` `CODE_REVIEW.md` → `ISSUES.md` 保留 history。

