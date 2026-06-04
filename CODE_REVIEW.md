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

---

## 项目亮点

- **SQL 注入防护** 🟢 — 100% 参数化查询
- **时区处理** 🟢 — 全局 `datetime.now(timezone.utc)`
- **Provider 隔离** 🟢 — 单源异常不影响其他标的
- **API 规范** 🟢 — 统一 `/api/v1/` 前缀 + 标准错误格式
- **日志统一** 🟢 — 全项目 `loguru`，无 `logging`/`print` 混用
- **架构分层** 🟢 — UI → API → Service → Collector/Storage，层级清晰
- **调度幂等** 🟢 — APScheduler 统一入口，配置驱动
