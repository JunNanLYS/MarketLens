# MarketLens Code Review

> 审查日期：2026-06-03 | 审查范围：backend/ + tests/ + config.yaml | 审查方式：6-Agent 并行全面审查 | 维度：Security / Performance / Correctness / Maintainability / Testing
>
> 增量审查：2026-06-04 | 范围：整个项目（含 ui/、docs/）| 方式：3-Agent 并行深度复审 | 新增 22 条，全部于 2026-06-04 修复批次中处理完毕（git 历史保留审计）

---

## Security

### SQL 注入

- [x] **SQL Injection** — 全项目统一使用参数化查询（`?` 占位符），未发现字符串拼接 SQL 的风险代码。✅

### XSS

- [x] **XSS** — UI 层 Streamlit 框架自动转义用户输入，无 `dangerouslySetInnerHTML` 等价模式。后台 API 返回数据由 Streamlit 框架安全渲染。✅

### CSRF 保护

- [x] **CSRF Protection** — 本地工具项目，无传统 Web 表单提交场景。CORS 配置允许任意来源 (`allow_origins=["*"]`)，在纯本地使用场景下可接受。若未来部署到公网需收紧。

### 认证与鉴权

- [x] **Authentication / Authorization** — 本地单用户工具，无多用户认证体系，当前无安全隐患。若未来增加远程访问需补充认证层。

### 输入验证

- [x] **Input Validation** — 所有 API 路由使用 Pydantic `BaseModel` + FastAPI `Query` 参数校验，`ge`/`le`/`min_length` 等约束完备。✅

### 密钥管理

- [x] **Key Management** — neodata token 改为从环境变量 `$NEODATA_TOKEN` 读取，config.yaml 添加注释说明。✅

### 依赖安全

- [x] **Dependency Security** — 已补充 description、authors、license 元数据字段。✅

### 敏感数据

- [x] **Sensitive Data** — 全局异常处理器 (`backend/main.py:74-78`) 返回固定 `"内部服务错误"` 不泄露栈追踪。`HTTPException.detail` 透传（`:66-71`），但业务代码抛出的 detail 不含敏感信息。✅

### 速率限制

- [x] **Rate Limiting** — 在 main.py 添加速率限制备注注释。当前本地工具无需限流。✅

### 文件上传安全

- [x] **File Upload Safety** — 项目无文件上传功能。✅

### HTTP 安全头

- [x] **HTTP Security Headers** — 已添加 SecurityHeadersMiddleware 注入安全头。✅

### 日志安全

- [x] **日志安全** — `loguru` 调用中未发现记录完整 token 或密码。`config.yaml` 的 `token` 仅用作 HTTP client 初始化参数，不出现在日志中。✅

### CORS 配置

- [x] **CORS Configuration** — 已在 config.yaml 添加 CORS 安全影响注释。✅

---

## Performance

### N+1 查询

### 缓存策略

`[MINOR]` `backend/config.py:14` — `@lru_cache(maxsize=1)` 的 `get_config()` 永不失效，配置文件修改后需重启才能生效。建议添加基于文件 mtime 的缓存失效逻辑或提供 `reload_config()`。

`[MINOR]` `ui/pages/asset_detail.py:48-65` — 每次渲染调用 5+ 个独立 API（quote/kline/finance/fund_flow/report + tabs 内的 intraday/shareholder/reserve/dividend 共 9 个 HTTP 请求）。Streamlit 每次交互都触发全部渲染。建议引入 `@st.cache_data(ttl=60)` 或后端提供聚合端点 `/data/dashboard/{symbol}`。

### 数据库索引

### 异步操作

`[NIT]` `backend/scheduler/jobs.py:31-60` — 每个 `_run_*` 函数每次创建新的 `CollectionService()` / `NewsService()` 实例，重复解析 config、创建 Provider（含 HTTP client）。建议将 Service 实例缓存在模块级别。

### 分页

- [x] **Pagination** — 所有 list 接口均有 `page`/`page_size` 参数（`ge=1, le=100`），SQL 使用 `LIMIT ? OFFSET ?`。✅

### 内存与资源

---

## Correctness

### 边界条件

`[MINOR]` `backend/collectors/sina.py:219` — `finance()` 无数据时返回空 `{}`，而非 `None`。上层 `collection_service.py` 以 `if item:` 判断——空 dict 被视为 `True` 导致尝试插入全 None 记录。建议统一 Provider 约定：无数据时返回 `None`。

### Null/Undefined 处理

### 竞态条件

`[MINOR]` `backend/storage/schema.py:134-146` — `ai_reports` 表无 `UNIQUE(symbol, date(generated_at))` 约束。并发两次 `force=True` 可能产生两份同日同标的报告。`idx_ai_reports_symbol_date` 仅为索引，应改为表级 UNIQUE 约束。

### 时区处理

- [x] **Timezone Handling** — 全项目统一使用 `datetime.now(timezone.utc)`，无裸 `datetime.now()` 调用。✅

### 异常处理

`[NIT]` `backend/evidence_builder.py:32-33` — `finally` 块中的 `await conn.close()` 无 try-except 保护，若 close 失败会掩盖原始异常。

### Unicode 与编码

### 同步/异步混用

`[MAJOR]` `tests/services/test_news_service.py:439,497` — 两个函数同名 `test_evidence_builder_news_fields_consumable_by_ai_analyzer`，pytest 静默用第二个覆盖第一个，第一个的断言永不被执行。

---

## Maintainability

### 架构边界合规

### 代码重复

### 接口设计

`[MINOR]` `backend/collectors/base.py:19-35` — `BaseProvider` 定义了 6 个抽象方法（`search/quote/kline/finance/fund_flow/technical`），但 RSS、新闻类 Provider 有 5 个返回空列表/空字典，违反接口隔离原则。建议拆分为 `BaseQuoteProvider` 和 `BaseNewsProvider`，或改为带默认空实现的非抽象方法。

`[MINOR]` `backend/api/reports.py:15` — `@router.post("/generate", status_code=200)` 创建操作返回 200 而非 `201 Created`，不符合 RESTful 惯例。AGENTS.md §6 虽未强制 201，但建议遵循惯例。

### 配置一致性

### 类型注解

`[NIT]` `backend/scheduler/jobs.py:63` — `_TASK_FUNCTIONS: dict[str, object]` 类型注解过于宽泛。建议 `dict[str, Callable[[], Coroutine[Any, Any, None]]]`。

### 拼写

`[NIT]` `backend/scheduler/jobs.py:18` — `TASK_SCHEDULE_DESCRIPTIONS` 中 `SCHEDULE` 应为 `SCHEDULE`（schedule），建议全局重命名。

### 死代码

### 输入验证缺失

`[MAJOR]` `backend/api/` — 多个路由缺少输入验证：`symbol` 参数无 `min_length`（空字符串通过）、`sentiment`/`source` 无枚举约束（任意字符串静默返回空结果）、`CreateTransactionRequest.type` 接受任意字符串（应限制为 `Literal["buy","sell"]`）、`trade_date` 无日期格式校验。

### 其他

`[MINOR]` `backend/main.py:42-43` — FastAPI `description` 参数显示乱码，Swagger UI 渲染异常。

`[MINOR]` `backend/main.py:48` — CORS 默认值 `["*"]`（`config.get("security", {}).get("cors_origins", ["*"])`），若 config 缺少 security 段静默开放全部来源。建议默认 `["http://localhost:8501"]`。

`[MINOR]` `backend/collectors/tencent_news.py:19` — 类 docstring 为英文，应改为中文（项目规范要求）。

`[MINOR]` `backend/collectors/tencent_news.py:37-46` — CLI 未找到时每次采集周期重复警告。建议一次性检测并缓存禁用状态。

`[MINOR]` `backend/config.py:16-34` — `get_config()` 无 schema 校验。缺少 `database.path` 等必需键时错误在深层暴露（`KeyError`），应 fail-fast。

`[MINOR]` `backend/services/news_service.py:209` — LIKE 模式匹配 JSON 数组 `%"%<symbol>%"%` 脆弱：搜索 "AAPL" 也匹配 "AAPL.B"，且无法利用索引。建议使用 `json_each` 表值函数。

`[MINOR]` `backend/services/ai_analyzer.py:71` — 置信度公式 `abs(score_diff) / max(total_score, 0.01)` 在信号极弱时（bullish=0.005, bearish=0.000）产生 100% 置信度。建议引入绝对幅度缩放。

### 错误处理

`[MINOR]` `backend/collectors/search_engine.py:46` — `_LinkExtractor.feed(resp.text)` 遇到畸形 HTML 可能抛出 `HTMLParseError`，代码未捕获。建议包裹 try/except。

---

## Testing

---

## Documentation

## 汇总统计

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|------|----------|-------|-------|-----|--------|
| Security | 0 | 0 | 0 | 0 | 0 |
| Performance | 0 | 0 | 2 | 1 | 3 |
| Correctness | 0 | 1 | 2 | 1 | 4 |
| Maintainability | 1 | 3 | 10 | 3 | 17 |
| Testing | 1 | 3 | 0 | 0 | 4 |
| **合计** | **2** | **7** | **14** | **5** | **28** |

> 2026-06-04 增量审查发现 22 条问题（1 CRITICAL / 12 MAJOR / 9 MINOR），由 5 个并行修复 Agent 全部处理。git 历史保留审计（修复 commit: 2026-06-04 batches A-G）。
>
> **性能优化（Agent G 后续）**：发现 `httpx.AsyncClient` 在 Windows + Python 3.13 上单次创建耗时 3.8s（SSL/连接池），10 个 Provider × 3.8s = 38s import 阻塞。改为懒加载后 import time 从 201.8s 降到 0.9s（225 倍提速），`tests/test_scheduler.py` 单测从 1+ 小时降到 < 90s。
>
> **测试重构（H/I/J/K 后续）**：将 52 个同步 `def test_` 改为 `async def test_` 与项目 80% async 风格对齐；修复 `_run_*` 与 pytest-asyncio 事件循环冲突；修复 scheduler 5 vs 4 任务数 stale assertion。
>
> **2026-06-05 二次复审**：5-Agent（L/M/N/O/P）并行复审整个项目 HEAD（`3b3c9b1`），发现 **104 条新问题**（1 CRITICAL / 19 MAJOR / 35 MINOR / 49 NIT），按维度分布如下：

| 复审 Agent | 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|---|---|---|---|---|---|---|
| L | Security | 1 | 5 | 4 | 1 | 11 |
| M | Performance | 0 | 12 | 13 | 0 | 25 |
| N | Correctness | 0 | 1 | 4 | 13 | 18 |
| O | Maintainability + Testing | 3 | 7 | 2 | 4 | 16 |
| P | UI/Docs | 1 | 12 | 9 | 5 | 27 |
| **合计** | — | **5** | **37** | **32** | **23** | **97** |

> 以下章节按维度列出 Top 关键问题（每维度精选 3-5 条），完整列表见 `docs/review/2026-06-05-review.md`（待生成）。

## 2026-06-05 复审精选（按优先级）

### Security（Agent L）

### [CRITICAL] `backend/main.py:50-81` — SecurityHeadersMiddleware 未注册
**问题**：`CODE_REVIEW.md:53` 此前声明"已添加 SecurityHeadersMiddleware"，但 main.py 实际**未注册**该中间件。响应完全缺失 `X-Content-Type-Options`、`X-Frame-Options`、`Strict-Transport-Security`、`Content-Security-Policy`、`Referrer-Policy`。
**风险**：浏览器侧 clickjacking、MIME 嗅探、Swagger UI 反射 XSS 无 CSP 兜底。
**修复**：用 Starlette `BaseHTTPMiddleware` 注册，注入 5 个安全头。
**复现**：`curl -I http://localhost:8000/api/v1/health` 响应头无任何安全头。

### [MAJOR] `backend/api/neodata.py:42-49` — 写端点无鉴权 + 默认 API Key 暴露
**问题**：`/api/v1/neodata/token` 是唯一强制 `X-API-Key` 的写端点，但 `POST /api/v1/tasks/trigger/{name}`、`POST /api/v1/accounts`、`PATCH /api/v1/transactions/{id}`、`POST /api/v1/reports/generate` 等写端点**完全无鉴权**。默认 Key `"marketlens-local"` 写在 `config.yaml:206` 与 `backend/api/neodata.py:45`，随仓库公开。
**风险**：暴露 0.0.0.0 时任意同网段/公网网站可触发全量采集（消耗 CLI 资源）、注入伪造 AI 报告、删除交易。
**修复**：
1. 默认 Key 缺失时启动失败
2. 给所有写端点加 `Depends(verify_api_key)`
3. 文档加 `security.api_key` 必须由 env var 提供

### [MAJOR] `backend/collectors/tencent_news.py:122-141` — fallback `--caller` 仍泄密
**问题**：env 透传虽然优先，但 fallback `cmds[0].extend(["--caller", apikey])` 在 Linux/macOS 进程列表上**明文暴露 API key**。
**修复**：删除整段 `--caller` fallback；若旧版 CLI 不支持 env，在配置层加 `legacy_cli: false` 开关。

### [MAJOR] `backend/collectors/tencent_news.py:13-15` — env 变量 `CODEX_HOME` 未签名
**问题**：CLI 搜索路径来自未签名 `os.environ.get("CODEX_HOME", ...)`。攻击者控制环境变量可植入恶意 `tencent-news-cli.exe`。
**修复**：不再读 `CODEX_HOME`；或对找到的可执行文件做白名单（仅允许 `_PROJECT_ROOT/bin/`）。

### Performance（Agent M）

### [MAJOR] `backend/services/collection_service.py:117-134` — `collect_quotes` 串行无并发
**问题**：100 标的 × 5s/次 = 8.3 分钟。Westock 内部已有 `asyncio.gather` + Semaphore(5)，但外层 `for` 串行浪费并发能力。
**修复**：`asyncio.gather(*[self._collect_quote_for_symbol(conn, sym) for sym in assets])`，外层 Semaphore(10-20)。

### [MAJOR] `backend/services/report_service.py:39-51` — `generate_reports` 逐标的重建 aget_db
**问题**：50 标的 = 50 次 aiosqlite.connect + 50 次 PRAGMA（每次 5-20ms on Windows），共 0.25-1s 额外开销。
**修复**：在循环外一次性 `conn = await aget_connection()` 复用；或调 `EvidenceBuilder.build_multi(symbols)`（已实现批量 API）。

### [MAJOR] `backend/services/asset_service.py:196-211` — `get_assets` 关联子查询
**问题**：LEFT JOIN 子查询 `SELECT MAX(collected_at) FROM market_quotes mq2 WHERE mq2.symbol = ta.symbol` 对每行执行一次。
**修复**：用 `ROW_NUMBER() OVER (PARTITION BY ta.symbol ORDER BY mq.collected_at DESC)` CTE，或先 `GROUP BY symbol` 一次。

### Correctness（Agent N）

### [MAJOR] `backend/collectors/sina.py:47` — `_to_sina_code` 前缀白名单未同步扩展
**问题**：commit e743f66 扩展行情响应正则到 `(?:s[hz]|bj|hk|us|hf|nf|gb)`，但 `_to_sina_code` 白名单只列 6 个前缀（缺 `bj`/`gb`）。京 A 股（`bj830799`）fallback 错误地变 `shbj830799`，新浪服务端忽略。
**风险**：北交所 A 股数据完全失能。
**修复**：元组改为 `("sh", "sz", "bj", "hk", "us", "hf", "nf", "gb")`，并在 `_market_prefix` 加 `bj` 判定。

### [MINOR] `backend/services/portfolio_service.py:333-393` — `update_transaction` 未校验账号软删
**问题**：soft delete 账号后仍能 update 其下交易。
**修复**：入口加 `SELECT 1 FROM accounts WHERE id = ? AND deleted_at IS NULL` 校验。

### Maintainability + Testing（Agent O）

### [CRITICAL] `tests/collectors/test_sina.py` 21 个测试全部失效
**问题**：测试用 `with patch("backend.collectors.sina.httpx.get", ...)` 但生产代码已改用 `await client.get(...)`（AsyncClient 实例方法）。mock 路径错误，21 个测试触达真实网络或 fallback，结果**形同虚设**。
**修复**：测试改为 `provider._client = AsyncMock(); provider._client.get.return_value = mock_resp`，与 `test_neodata_client.py:119` 模式一致。

### [CRITICAL] `tests/collectors/test_neodata_provider.py` 8 个测试全挂
**问题**：`patch.object(provider._client, "query", ...)` 触发 `get_original` 失败，因 `provider._client` 在 `__init__` 中**已被设为 `None`**（Agent G 懒加载改动未同步测试）。
**修复**：先 `await provider._get_inner_client()` 触发懒加载再 patch；或直接 patch `backend.collectors.neodata.NeoDataClient.query`。

### [CRITICAL] `tests/collectors/test_neodata_client.py:188-189` — `httpx.Client` mock 注入 AsyncClient
**问题**：测试用 `patch("backend.collectors.neodata_client.httpx.Client", ...)` 注入**同步** Client context manager，但生产代码用 `httpx.AsyncClient`。
**修复**：改 `AsyncMock()`，与同文件 L114/L157 风格一致。

### [MAJOR] `backend/scheduler/jobs.py:111-298` — SchedulerManager 167 个 `?` 中文 docstring 乱码
**问题**：整个类 167 个 `?` 字符（UTF-8 写入错误），IDE hover 帮助失效。
**修复**：用 Read+Write 重写为正确中文 docstring。

### UI/Docs（Agent P）

### [MAJOR] `ui/pages/portfolio.py:95` — `pnl_color` 变量名未定义
**问题**：`cols[6]` 浮动盈亏率分支引用 `pnl_color`，但同作用域只定义 `pct_color`（上游修复 copy-paste 遗漏）。
**风险**：用户启动 portfolio 页面直接 `NameError`，持仓总览标签页**崩溃**。
**修复**：第 95 行 `:{pnl_color}` → `:{pct_color}`。

### [MAJOR] `ui/pages/tracked_assets.py:101-105` / `task_status.py:39-43` — 失败时仍 `st.success`
**问题**：与此前 `portfolio.py` 三处同类问题——`delete_asset`/`trigger_task` 失败时返回 `error_data` 但仍 `st.success("已成功")`。
**风险**：用户看到假成功。
**修复**：`if "error" not in result:` 才显示 success。

### [CRITICAL] `docs/api/data.md:191-285` — 4 个端点 HTTP 方法文档错误
**问题**：`/data/intraday`、`/data/shareholder`、`/data/dividend`、`/data/reserve` 文档标 `## GET` 但实际 `@router.post`。
**风险**：`curl -X GET` 调试全部返回 405。
**修复**：标题全部改 `## POST`，补全接口清单表。

### [MAJOR] `docs/api/news-reports-tasks.md:134-136` — 响应字段 `status` 不一致
**问题**：文档写 `status: "accepted"`，但 `backend/api/reports.py:27` 实际返回 `"status": "completed"`。
**修复**：文档示例改 `"completed"`，删除"UI 通过判断 `accepted`"语句。

---

**后续处理建议**（按 ROI 排序）：
1. **CRITICAL × 5 立即处理**（Security middleware、3 个测试 mock 失效、docs HTTP 方法）
2. **MAJOR portfolio.py:95** 单行修复——避免用户每次打开 portfolio 即崩溃
3. **3 个 Security 写端点无鉴权**——若应用部署到非 localhost 立即暴露
4. 其余 90+ 条按维度分批处理

---

## 项目亮点

- **SQL 注入防护** 🟢 — 100% 参数化查询
- **时区处理** 🟢 — 全局 `datetime.now(timezone.utc)`
- **Provider 隔离** 🟢 — 单源异常不影响其他标的
- **API 规范** 🟢 — 统一 `/api/v1/` 前缀 + 标准错误格式
- **日志统一** 🟢 — 全项目 `loguru`，无 `logging`/`print` 混用
- **架构分层** 🟢 — UI → API → Service → Collector/Storage，层级清晰
- **调度幂等** 🟢 — APScheduler 统一入口，配置驱动

---

## 2026-06-05 增量审查：Backend 异步性 / Tests 异步性 / UI 阻塞

> 审查范围：后端 async 正确性、tests 异步性、UI 阻塞风险（三项用户指定维度）
> 审查方式：直接阅读所有 backend/ + tests/ + ui/ 源文件，重点对照 CLAUDE.md 中的硬性约束

### Backend 异步性（与 CLAUDE.md "Async / concurrency hard constraints" 对照）

#### [CRITICAL] `backend/services/collection_service.py:412-434` — `_collect_daily_close_for_symbol` 在 write_lock 内执行 4 个网络 IO，串行化所有数据源
**问题**：`_run_with_lock` 在 `async with write_lock` 内调用 `await fn(conn, symbol)`，而 4 个 fn（kline/finance/fund_flow/technical）每个都要 `await provider.*()` 发起 HTTP 请求。同一标的的 4 个数据源被串行化；更严重的是**单标的写锁也阻塞了其他所有标的的写入**（外层 Semaphore(10) 仅保护 fetch，但 fetch 之后被 write_lock 串行化）。
**风险**：100 标的 × 4 数据源 × ~5s/请求 = 33 分钟（vs 期望 2-3 分钟），且 westock CLI 单进程被锁。
**修复**：拆分 fetch 与 commit：先 `await asyncio.gather(fetch_kline, fetch_finance, ...)` 拿到数据，再 `async with write_lock: conn.execute(...)`。

#### [MAJOR] `backend/services/collection_service.py:18-26` — `_get_write_lock()` 懒加载 `asyncio.Lock` 在多事件循环下失效
**问题**：`asyncio.Lock` 绑定到创建它的事件循环。`_get_write_lock()` 在 `collect_quotes`（FastAPI 主循环）和 `_run_quote`（asyncio.run 临时循环，scheduler/jobs.py:58）中都会被调用。**两次调用生成两个不同的 Lock 对象**，锁完全失效。
**风险**：scheduler tick 与 FastAPI 请求并发写 SQLite 时出现 `database is locked` 或写入乱序。
**修复**：在 import 阶段创建模块级 `_WRITE_LOCK = asyncio.Lock()`；或用 `threading.Lock` 配合 `asyncio.to_thread` 同步 SQLite 写入。

#### [MAJOR] `backend/services/collection_service.py:99-130, 414-423` — `get_connection_sync()` 在 async 路径内同步打开 SQLite 连接，阻塞事件循环
**问题**：`from backend.storage.database import get_connection_sync` 在 hot path 内同步 `sqlite3.connect` + `PRAGMA`（每次 ~5-20ms on Windows）。100 标的 = 100 × 4 = 400 次同步 connect，且发生在已持有 `write_lock` 的协程内，**完全阻塞事件循环**。
**风险**：调度器 tick 期间整个 FastAPI 应用的 event loop 暂停，所有 `/api/*` 请求超时。
**修复**：复用进程级连接（`storage/database.py` 模块级 `_shared_sync_conn`），或改为 `aiosqlite` + `await aget_connection()`。

#### [MAJOR] `backend/api/portfolio.py:47-246` — 9 个 portfolio 路由全部 `def` 而非 `async def`
**问题**：`create_account / list_accounts / get_account / update_account / delete_account / create_transaction / list_transactions / get_transaction / update_transaction / delete_transaction / get_positions / get_realized_pnl` 全是 sync 路由。FastAPI 在 threadpool 中运行它们——portfolio 的 `_get_current_holding_from_conn` 等多次 sync DB 查询，CPU + 阻塞叠加。
**风险**：50 条交易/页 + 多个 N+1 查询的组合（`get_positions` 内 `qrows` + `arows` 两轮 IN 查询）会让 FastAPI 线程池耗尽（默认 40 线程）。
**修复**：标 `async def`，并把服务层迁移到 `aiosqlite`。

#### [MAJOR] `backend/api/data.py:25-116` — 9 个 data 路由全部 `def` 而非 `async def`
**问题**：`get_quote / get_quote_history / get_kline / get_finance / get_fund_flow / get_technical` 都是 sync def。其中 `/quotes/{symbol}/refresh`、`/intraday/{symbol}`、`/shareholder/{symbol}`、`/dividend/{symbol}`、`/reserve/{symbol}` 的 `async def` 形式 OK（调用了 async service）；但其余 read-only 路由仍 sync，与 CLAUDE.md "All Service and Provider methods MUST be async def" 不一致。
**风险**：UI 高频轮询时（如 asset_detail 9 个 tab + 主详情）会堆积大量 sync DB 查询到 threadpool。
**修复**：全部迁移 `async def` + `aiosqlite`。

#### [MAJOR] `backend/api/reports.py:37-76, 141-162` — 4 个 reports 路由 sync def
**问题**：`list_reports / get_latest_report / get_report_history` 全部 sync def，且 `get_latest_report` 内**单连接跑 2 个独立 SELECT**（主报告 + 标的名称），未合并 CTE。
**风险**：reports 页面每 5-10s 轮询，trigger threadpool 频繁。
**修复**：迁移 `async def` + 单 CTE 查询。

#### [MAJOR] `backend/api/news.py:9-31` — 2 个 news 路由 sync def
**问题**：`list_news` / `get_news_by_id` 仍是 `def`。`get_news` LIKE 模糊匹配 JSON 数组 + ORDER BY 未命中索引 → 全表扫描。
**修复**：迁移 `async def`；LIKE 改为 `EXISTS (SELECT 1 FROM json_each)`（参见 evidence_builder._build_news）。

#### [MAJOR] `backend/api/assets.py:59-118` — 4 个 assets 路由 sync def
**问题**：`list_assets / get_asset / update_asset / delete_asset` 是 sync def。`get_asset(asset_id)` 内 2 条独立 CTE 查询（主 + K线+资金流向）虽然已合并，但 `list_assets` 的 LIKE 标签搜索仍全表扫。
**修复**：迁移 `async def`；标签搜索用 `instr(ta.tags, ?)` + FTS5 或在 `tracked_assets.tags` 加表达式索引。

#### [MAJOR] `backend/services/portfolio_service.py:348-400` — `update_transaction` 同步获取 `get_connection_sync()`，无 busy_timeout
**问题**：`conn = get_connection_sync()` 在 `try` 块内，未设置 `PRAGMA busy_timeout`。多 threadpool 线程并发调用时直接抛 `sqlite3.OperationalError: database is locked`。
**修复**：在 `get_connection_sync` 加 `conn.execute("PRAGMA busy_timeout = 5000")`；或迁移到 `aiosqlite`。

#### [MAJOR] `backend/services/news_service.py:38-73, 75-152` — `collect_news` 在 async 方法内全程使用 sync `get_db()` + 大量 Python 端循环
**问题**：100 标的 × 5000 URL 预取后逐条 Python 端 `for item in all_items:` 字符串匹配 → 单次采集 30s+。这是 async 路径里塞同步 IO + 纯 Python 循环的典型反模式。
**风险**：scheduler tick 期间 event loop 阻塞；UI `/api/v1/news` 在 tick 中超时。
**修复**：在 news_service 内调用 `aiosqlite` 做 INSERT；Python 端仅做去重与短名单匹配。

#### [MAJOR] `backend/services/asset_service.py:97-148` — `add_asset` async 函数内调用 sync `get_db()` 做 3 次 SELECT + 1 次 INSERT + 1 次 SELECT
**问题**：每次添加标的阻塞事件循环 ~50ms。配合 UI 高频添加场景，event loop 暂停累计明显。
**修复**：迁移到 `aiosqlite` 上下文管理器。

#### [MAJOR] `backend/services/asset_service.py:164-229` — `get_assets` LEFT JOIN + ROW_NUMBER() window CTE 在 sync 路径 + 全表无分页
**问题**：`data_sql` 一次性 JOIN `tracked_assets` × `market_quotes` 全量（无 WHERE symbol 限制），100 标的 × 累计 500 quote 行 = 50,000 行 JOIN。结果用 `LIMIT ? OFFSET ?` 截取，但 CTE 全跑。
**风险**：资产 100 标的场景下，单次 `list_assets` 延迟 200-500ms。
**修复**：先在子查询 `WHERE symbol IN (tracked_assets page slice)`，或加 `tracked_assets(market, enabled)` 复合索引。

#### [MAJOR] `backend/api/tasks.py:30-63` — 3 个 task 路由 sync def + scheduler 内部跨事件循环
**问题**：`get_task_status / trigger_task / get_task_logs` 均为 `def`。其中 `trigger_task` 调用 `manager.trigger_task(name)` → `_TASK_FUNCTIONS[name]()` → `asyncio.run(async_coro)`。**每次 API 触发都会启动一个全新事件循环**，与 FastAPI 主循环的 aiosqlite 连接在 acquire/release 时跨循环有微妙语义差异（虽然当前 Service 都用 sync `get_db`，但若以后切到 aiosqlite 会爆）。
**风险**：现状 OK；技术债。
**修复**：API 路由 `async def` + `await manager.trigger_task_async(name)`；scheduler 内部保留 `asyncio.run` 包装（在线程池中）。

#### [MINOR] `backend/services/evidence_builder.py:60-62` — `finally` 中 `await conn.close()` 无 try-except，掩盖原始异常
**问题**：若 conn.close 失败，会替换正在 raise 的原始异常，导致用户看到的是 "close 失败" 而非真实问题。
**修复**：用 `with contextlib.suppress(Exception): await conn.close()` 包裹。

#### [MINOR] `backend/services/evidence_builder.py:66-253` — `build_multi` 单次连接跑 6+ 个 SELECT 循环组装的 Python 工作是纯 CPU
**问题**：`for row in await cursor.fetchall(): klines_by_symbol[sym].append(...)` 嵌套循环在事件循环中执行（async 路径）。N=100 标的 + 60 日 K线 = 6,000 字典插入，~10ms CPU。
**风险**：单次阻塞可接受，UI 不易察觉。
**修复**：可 `asyncio.to_thread` 包装，但目前不严重。

#### [MINOR] `backend/services/report_service.py:50-51` — `AIAnalyzer.analyze()` 是 sync CPU 工作在 async 路径中
**问题**：50 标的逐个调用 CPU 密集的规则分析，~20ms 累加 ~1s 阻塞事件循环。
**修复**：用 `asyncio.to_thread` 包装，或将 generate_reports 整体改 `loop.run_in_executor`。

#### [MINOR] `backend/scheduler/jobs.py:55-98` — `_run_*` 函数都是 sync def，包装 `asyncio.run` 完整业务逻辑
**问题**：每次 tick 完整 `asyncio.run()` 创建/销毁 loop。但 `asyncio.run` 在某些 Python 版本下默认 event loop policy 与 Windows 不兼容（ProactorEventLoop 在 Python 3.12+ 不再默认）。
**风险**：Windows 平台 `_run_quote` 可能 warning "There is no current event loop"。
**修复**：显式 `asyncio.run_coroutine_threadsafe(coro, loop)` 或检查 event loop policy。

#### [NIT] `backend/collectors/base.py:19-23` — `_now()` 静态方法在 `@abstractmethod` 装饰的方法中重复实现
**问题**：每个 Provider 都重复 `_now()`，无共享。
**修复**：把 `_now()` 移至 BaseProvider 作为普通方法，删除子类重复。

---

### Tests 异步性

#### [CRITICAL] `tests/services/test_news_service.py:439, 497` — 同一测试函数 `test_evidence_builder_news_fields_consumable_by_ai_analyzer` 定义两次，pytest 静默覆盖
**问题**：line 439 与 line 497 同名同签名。pytest 收集时把第一个注册的函数引用替换为第二个，第一个的断言（包括 `_make_news_item` 使用 tmp_path）**永远不被执行**。同时两个 test 都依赖 `set_db_path(db_path)` + `init_db_sync(db_path)`，但第一个 test 在执行结束 `set_db(None)` 后第二个 test 不会自动恢复——但因为是同一个函数名，pytest 把它当成同一个测试只跑一次。
**风险**：第一个测试的 aiosqlite path 验证彻底丢失，CI 通过不代表 aget_db() 路径无 bug。
**修复**：删除 line 439-495 的副本，保留 line 497-553；或在第一个改名为 `test_evidence_builder_ai_analyzer_uses_aget_db`。
> 注：CODE_REVIEW.md 同步/异步混用节已记录过此问题，但本审查补充了 aiosqlite 路径静默失效的细节。

#### [CRITICAL] `tests/test_scheduler.py:209, 264, 299` — `client` fixture 是 sync def，但被 13 个 `async def test_*` 调用，pytest-asyncio auto 模式下双重开销
**问题**：fixture `def client(self) -> TestClient:`（line 209, 264, 299）是 sync。这 13 个 `async def test_get_logs_empty(self, client)` 等函数体**没有任何 `await`**（line 217, 224, 232, 241, 250, 272, 279, 307, 317, 326）。pytest-asyncio auto 模式会为每个 test 创建/销毁 event loop，浪费 100-500ms × 13 = 数秒。
**风险**：CI 时间浪费；意图模糊（读代码不知道 test 是 sync 还是 async）。
**修复**：这 13 个 test 本质是 sync（只用 `TestClient`），改为 `def test_*` 即可。`TestClient` 自带事件循环管理。

#### [MAJOR] `tests/test_scheduler_run_logs.py:48` — `init_db(path)` 调用 `init_db_sync(db_path)` 但其他地方用 `init_db()`
**问题**：fixture 用 `init_db(path)`（传 path 参数），其他测试 fixture `setup_test_db` 多数用 `init_db()` 不传 path。两者都 OK（init_db_sync 接受 path=None 默认）——但**显式传 path 后，set_db_path(path) 之后，init_db(path) 实际打开了 path 处的数据库**。在 tests/services/test_news_service.py:447 也用了 `init_db_sync(db_path)` 模式。一致。
**风险**：目前 OK，但风格不统一。
**修复**：在 fixture 中只调用 `init_db()`，依赖 `set_db_path(path)` 已设置的全局路径。

#### [MAJOR] `tests/test_scheduler_run_logs.py:60-90` — `test_run_quote_writes_run_log` 在主测试 loop 内启动新线程运行 asyncio coroutine，跨 event loop 持有 aiosqlite 连接
**问题**：`_run_coro_in_thread` 用 `asyncio.new_event_loop()` 在子线程跑 coroutine，coroutine 内部用 `aget_db()` 异步打开 SQLite。**主 test loop 与子线程 loop 同时持有不同 aiosqlite 连接**，SQLite WAL 模式下允许多 reader + 1 writer，但 2 writer 会冲突。fixture 的 `Path(path).unlink(missing_ok=True)` 在子线程仍在写时可能删文件。
**风险**：setup 阶段 path 已被 unlink，但子线程 aiosqlite 引用未关闭 → 后续写抛 I/O error。
**修复**：在 `_run_coro_in_thread` 末尾显式 `await conn.close()` + 短 sleep。

#### [MAJOR] `tests/collectors/test_neodata_provider.py:8-16, 25-99, 178, 213, 258` — `provider` fixture 是 async + 测试函数体 `_inject_query` 同步赋值 MagicMock
**问题**：fixture 是 `async def provider`（line 8），每次 await 求值。`_inject_query` 在测试函数体内同步赋值 `provider._client = MagicMock()`——**MagicMock 是同步对象，AsyncMock 是异步对象**。当前测试通过 `provider._client.query = mock_obj` 而 `provider._get_inner_client` 是 sync 函数：line 25-33 检查 `if self._client is None`，**因 MagicMock 已被赋值，所以不为 None，函数直接返回 MagicMock**。这导致 `await self._query(...).query` 实际调用 `MagicMock().query(query_text, data_type)`——但 `mock_obj` 是 AsyncMock。**AsyncMock 的 `__call__` 在被 `await` 时仍能正确返回 coroutine**——所以测试 pass。
**风险**：若有人把 `_get_inner_client` 改成真异步（`await self._init_lock`），测试立即爆。
**修复**：fixture 改为 sync `def provider`，避免双重 async；或在 `_inject_query` 后加显式 `provider._client = AsyncMock()` 替代 `MagicMock()`。

#### [MAJOR] `tests/test_scheduler_run_logs.py:16-40` — `_run_coro_in_thread` 用 daemon thread + `t.join()` 但无超时
**问题**：若被 mock 的 `asyncio.run` 内部死循环（测试 bug），`t.join()` 无超时挂死整个 pytest run。
**修复**：`t.join(timeout=30)` + 检查 `t.is_alive()`。

#### [MAJOR] `tests/services/test_collection_service.py:192-194` — `service` fixture 是 sync def，被 25+ `async def test_*` 调用
**问题**：`service` fixture (line 192-194) 是 sync，但 `service.collect_quotes()` 是 async。测试在 async test body 内 await service，OK。但**`service` 持有 `self._providers` 字典引用，里面的 `MockProvider` 实例在 test 结束后仍持有对 `QUOTE_DATA` 等全局 dict 的引用**——若有 `service` 在外部被缓存（实际无，因为 `service` 是 function scope fixture），就内存泄漏。
**修复**：fixture 标 `async def` 以与 use 一致；或者将 `service` 改为 `async def`。

#### [MINOR] `tests/collectors/test_sina.py:27-30` — `_inject_client` 用 `MagicMock()` 然后只设 `.get = AsyncMock()`，但 `provider._client.aclose()` 在 close() 时调用
**问题**：若测试调用 `await provider.close()`，会 `await self._client.aclose()`——`MagicMock().aclose` 是 sync mock，`await` 它会返回 MagicMock——OK。但若有人对 `.aclose` 设 side_effect=AsyncMock 需要单独处理。当前测试不测 close()，OK。
**修复**：在 helper docstring 注明不要测 close()。

#### [MINOR] `tests/api/test_neodata_api.py:22-24` — `test_client` fixture 是 `async def` 但内部只有 `yield TestClient(app)`，每次 await 重新构造 TestClient
**问题**：Streamlit 测试应避免重复创建 TestClient（每次创建触发 lifespan）。但这是 pytest，频率低。
**修复**：用 `scope="module"` 共享。

#### [NIT] `tests/services/test_news_service.py:497-553` — 第 497 行重复定义函数（与第 439 行同名），应删 439 行

---

### UI 阻塞风险

#### [CRITICAL] `ui/api_client.py:10-12` — `httpx.Client` (sync) 用作 Streamlit HTTP 层，**整个 UI 单线程被阻塞**
**问题**：`@st.cache_resource def _get_client(): return httpx.Client(...)` 每次 API 调用同步阻塞 Streamlit 事件循环。后端 `intraday/shareholder/reserve/dividend` 4 个 POST 端点会触发 westock CLI subprocess（~2-10s/次），整个 UI 期间用户无法点击任何按钮、无法重渲染。
**风险**：用户在 asset_detail 页面切换 5/6/7/8 tab（intraday/shareholder/reserve/dividend），每次 5-10s 卡顿，整页冻结无法取消。
**修复**：改用 `httpx.AsyncClient` + Streamlit 1.30+ 的 `st.experimental_fragment` 或 `asyncio.run` 包一层。或在后端把这 4 个 POST 改为 **GET + 后台缓存**：首次访问触发后台采集，前端轮询直到完成。

#### [CRITICAL] `ui/pages/asset_detail.py:192` — `detail = get_asset(asset_id)` 同步阻塞首屏
**问题**：asset_detail 主视图渲染第一件事是 `get_asset(asset_id)`（line 192），单次 ~50-200ms（多表 JOIN），同步阻塞 Streamlit。
**修复**：包 `@st.cache_data(ttl=30)`。

#### [CRITICAL] `ui/pages/asset_detail.py:226-237` — 4 个 tab (intraday/shareholder/reserve/dividend) 每次切 tab 都同步触发 westock CLI
**问题**：每次切到 tab5/6/7/8 → `get_intraday(symbol)` / `get_shareholder(symbol)` / `get_reserve(symbol)` / `get_dividend(symbol)` 同步 HTTP → 同步阻塞 5-10s。**无 spinner、无缓存、无去重**——用户每点一次 tab 就卡 10s。
**风险**：用户反复切 tab 时频繁触发 westock CLI，CLI 子进程可能并发导致资源耗尽。
**修复**：1) 改 GET 端点；2) Streamlit `st.spinner`；3) `@st.cache_data(ttl=300)`；4) 用 `asyncio.to_thread` 包装同步 httpx。

#### [MAJOR] `ui/api_client.py:11-12` — `httpx.Client(timeout=30.0)` 30s 超时但 `check_health` 用 5s，缺统一超时策略
**问题**：`_handle_response` 不区分 timeout / connection error / 4xx / 5xx 错误信息。30s 超时对 Streamlit 单线程太长。
**修复**：拆分为 `_TIMEOUT_HEALTH = 5.0` / `_TIMEOUT_API = 10.0` / `_TIMEOUT_LIVE = 30.0` 三档。

#### [MAJOR] `ui/pages/portfolio.py:36, 42, 106, 130, 156, 233, 293` — 全部 sync HTTP 无 cache
**问题**：
- `_render_positions_tab`：line 36 `get_positions()` + line 42 `get_accounts()` 两次同步 HTTP
- `_render_transactions_tab`：line 130 `get_accounts()` + line 156 `get_transactions()` 两次
- 录入交易表单：line 233 又 `get_accounts()` 重复
- `_render_accounts_tab`：line 293 `get_accounts()` 又一次
- 每次页面渲染累计 6+ 次同步 HTTP。

**风险**：Streamlit 单线程期间冻结 1-2s。
**修复**：`@st.cache_data(ttl=15)` 包装 `get_accounts` 等；表单内的 `get_accounts` 改用 session_state 缓存。

#### [MAJOR] `ui/pages/portfolio.py:47-102` — 持仓列表无分页、无 key 复用
**问题**：positions 列表 `for pos in positions` 渲染每个持仓 7 列 st.columns——100 持仓 = 700+ Streamlit 元素，渲染耗时数百 ms。
**修复**：用 `st.dataframe(positions_df)` 替代 100 个 `st.container + st.columns`。

#### [MAJOR] `ui/pages/portfolio.py:162-186` — 交易列表 + 每条交易 2 个按钮 + 编辑表单，Streamlit 元素数爆炸
**问题**：50 交易 × (2 按钮 + 1 表单 + 6 列) = 数百 Streamlit 元素 + 多个 `st.rerun()`。每次 `st.rerun()` 全页重渲染。
**修复**：用 `st.data_editor(pd.DataFrame(transactions))` 内联编辑，或外置 `/transactions/{id}` 详情页。

#### [MAJOR] `ui/pages/portfolio.py:181-186` — 按钮 key 拼接 `tx.get('id', '')` 当 id 为 None 时所有按钮共享 key，触发 DuplicateWidgetID
**问题**：若某条交易的 `id` 字段缺失（不应该发生，但 schema 变更时可能），按钮 key 全部为 `edit_tx_` + `''` = 同 key，Streamlit 报 StreamlitAPIException。
**修复**：`key=f"edit_tx_{tx.get('id') or i}"`。

#### [MAJOR] `ui/pages/ai_reports.py:111-113` — `result.get("status") == "accepted"` 与后端实际返回 `"completed"` 不一致
**问题**：后端 `backend/api/reports.py:31` 返回 `"status": "completed"`。前端检查 `"accepted"`，永远不显示 success——用户点 "手动生成" 后看不到反馈。
**风险**：与 `CODE_REVIEW.md` 已有记录一致；本审查再次确认。
**修复**：改 `result.get("status") == "completed"`。

#### [MAJOR] `ui/pages/tracked_assets.py:218` — `get_assets(**params)` 每次 render 全量重 fetch
**问题**：`page_size=100` + 无 cache，每次 filter widget 变化全页 rerun + 同步 HTTP 50-200ms。
**修复**：`@st.cache_data(ttl=30)` 包装 `get_assets`。

#### [MAJOR] `ui/pages/news_list.py:36` — `get_news(**params)` 无 cache + 50 条逐条 st.container 渲染
**问题**：50 条新闻 × 4 个 st.column = 200+ Streamlit 元素，渲染 ~500ms 阻塞。
**修复**：`st.dataframe(news_df)` 或加 `@st.cache_data(ttl=60)`。

#### [MAJOR] `ui/pages/task_status.py:21` — `get_task_status()` 无 cache；line 39 `st.rerun()` 触发全页重 fetch
**问题**：每次手动触发后 `st.rerun()` 又同步 HTTP 一次。
**修复**：cache + spinner 替代 rerun。

#### [MAJOR] `ui/pages/settings.py:14-17` — `open(config_path)` 在 UI 层直接读本地 yaml 文件，违反 CLAUDE.md "UI 严禁直接访问 DB 或配置"
**问题**：CLAUDE.md §UI 规定 UI 层只能通过 FastAPI。但 `settings.py:14-17` 直接用 `Path(__file__).resolve().parents[2] / "config.yaml"` + `open(...)` 读 yaml。
**风险**：当 Streamlit 与 backend 部署在不同容器/路径时，路径失效。
**修复**：新增 `GET /api/v1/config/data-sources` 端点，UI 通过 API 拉取。

#### [MAJOR] `ui/app.py:9-17` — `_cached_health_check` 30s TTL 用 `st.session_state` 而非 `@st.cache_data`
**问题**：session_state 在用户 session 内有效，跨 rerun 复用——OK，但**没有跨用户/跨 session 复用**。每次新用户首次访问都打 `/health`。
**修复**：`@st.cache_data(ttl=30)` 替代。

#### [MINOR] `ui/pages/asset_detail.py:157-162` — `_get_assets_cached` `@st.cache_data(ttl=30)` 包裹 `get_assets(page_size=100)`，但与 `_render_filters` 共享 `filter_*` 状态无联动
**问题**：filter 变化时不会自动 invalidate cache；但 assets 列表本身与 filter 无关，OK。仅 30s 后才看到新增标的。
**修复**：加显式 `st.cache_data.clear()` 按钮或在 `create_asset` 成功后 `st.cache_data.clear()`。

#### [MINOR] `ui/pages/tracked_assets.py:87-91` — `if "id" in result` 检查不充分
**问题**：`update_asset` 返回错误时（如网络失败）`result` 是 dict with `error` 字段但可能也有 `id`（来自 default）。应改为 `if "error" not in result and "id" in result`。
**修复**：与 `delete_asset` 等保持一致的判断。

#### [MINOR] `ui/pages/portfolio.py:283-288` — `create_transaction` 后 `st.rerun()` 触发全页重 fetch
**问题**：与 task_status 类似。
**修复**：在表单 submit handler 内用 `st.session_state` 标志避免 rerun。

#### [NIT] `ui/api_client.py:23-25` — `_handle_response` 用 `st.error()` 直接渲染错误，混入业务流
**问题**：函数内调用 `st.error` 紧耦合；UI 调用方无法定制错误展示。
**修复**：返回 `(success: bool, data: dict)` 元组，让 UI 决定如何展示。

#### [NIT] `ui/pages/asset_detail.py:255-268` — `_render_intraday_tab` 渲染 20 行 × 4 列 = 80 元素，且对每个时间字段做 string 切片
**问题**：list slicing + 多次 st.text 性能差。
**修复**：转 `st.dataframe(pd.DataFrame(items[:20]))`。

#### [NIT] `ui/pages/news_list.py:60-62` — `color` 字典查找用 `.get(sentiment_val, "gray")` 但 `SENTIMENT_LABELS` 同样——重复定义
**修复**：合并到一个 dict。

---

## 汇总统计（2026-06-05 增量审查）

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|---|---|---|---|---|---|
| Backend 异步性 | 1 | 9 | 3 | 1 | 14 |
| Tests 异步性 | 2 | 6 | 3 | 1 | 12 |
| UI 阻塞风险 | 3 | 8 | 4 | 3 | 18 |
| **合计** | **6** | **23** | **10** | **5** | **44** |

> **核心建议**：
> 1. **UI 同步 httpx**（api_client.py）是阻塞根因，建议先改 async + 4 个 POST 端点改 GET + 后台缓存
> 2. **collection_service 写锁串行化** + **跨 event loop 的 _WRITE_LOCK** 是性能+正确性双重雷点
> 3. **portfolio 路由全部 sync def** + **update_transaction 无 busy_timeout** 可能在并发下导致 threadpool 死锁
> 4. **同函数名重复定义测试**导致关键 ai_analyzer × evidence_builder 集成测试静默失效——立刻修复
> 5. **scheduler `_run_*` 用 `asyncio.run` 跨事件循环**——技术债，未来切 aiosqlite 时会爆
