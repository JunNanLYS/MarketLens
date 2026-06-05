# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

**MarketLens is a single-user, local-first tool.** It runs on the developer's own machine, talks to public financial data sources, and stores everything in a local SQLite file. There is no remote user base, no multi-tenant data, no internet-facing deployment.

When reviewing code or assessing risks, apply this **threat model**:

- ✅ **Real risks worth flagging** — data corruption, race conditions in the UI/server (Streamlit reruns, concurrent API calls), timezone/locale bugs, misconfigured config, inconsistent docs, accessibility for the user, broken tests giving false confidence.
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
- **Concurrency** — Streamlit rerun can race with API requests; scheduler tick can overlap with manual triggers; check-then-act in `update_transaction`/`delete_transaction`
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
- **Streamlit `@st.cache_data`** — which of the 9 detail-page tabs are un-cached?
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
You stare at the Streamlit 9-tab detail page daily. Color blindness, doc/code drift, dead UI options affect you.

- **P&L red/green only** — ~8% of male users can't distinguish
- **Cache TTL reasonableness** — quote 15min cycle, UI 30s reasonable
- **API doc/code sync** — `docs/api/*.md` vs `backend/api/*.py` field names, status codes
- **Emoji-only buttons** — `st.button("✏️")` with no `help=` / `aria_label`
- **Dead UI options** — `running` filter that never matches
- **Hidden labels** — `label_visibility="collapsed"` removes accessible name

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

# Run Streamlit UI
uv run streamlit run ui/app.py

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
```

## Architecture

MarketLens is a **local-first, evidence-driven AI financial research assistant**. It tracks assets → auto-collects data → builds evidence packages → runs AI analysis → produces structured reports. All data stays in local SQLite.

### Layered design (top to bottom)

```
Streamlit UI (ui/)         — display only; never touches DB directly
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

- **Python ≥ 3.13** with `uv` package manager; use `.venv`, never system Python
- **Node.js ≥ v18** required for `westock-data-clawhub` CLI (WeStock data source)
- All comments and docstrings in **Chinese**
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
ui/                  → Streamlit pages; NEVER touches DB directly, must go through FastAPI
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

See `CODE_REVIEW.md` for a comprehensive audit covering correctness, performance, and maintainability findings. Notable items:
- `BaseProvider` defines 6 abstract methods but news/RSS providers only implement `search()` — the rest return empty stubs
- `ai_reports` table uses an index rather than a UNIQUE constraint on `(symbol, date(generated_at))`, risking duplicate reports
- `raw_data` table has no auto-cleanup and will grow unbounded
- Service instances are recreated per scheduler tick rather than cached

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
