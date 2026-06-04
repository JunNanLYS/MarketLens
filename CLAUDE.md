# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Task Completion Checklist

After **every** task, execute these steps in order:

### 1. Error Check

Scan all modified files for syntax errors or statically detectable logic issues. If errors are found, fix them and **restart from step 1**.

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
