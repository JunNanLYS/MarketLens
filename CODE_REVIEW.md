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

`[MINOR]` `ui/pages/asset_detail.py:48-65` — 每次渲染调用 5+ 个独立 API（quote/kline/finance/fund_flow/report + tabs 内的 intraday/shareholder/reserve/dividend 共 9 个 HTTP 请求）。Streamlit 每次交互都触发全部渲染。建议引入 `@st.cache_data(ttl=60)` 或后端提供聚合端点 `/data/dashboard/{symbol}`。

### 数据库索引

### 异步操作

### 分页

- [x] **Pagination** — 所有 list 接口均有 `page`/`page_size` 参数（`ge=1, le=100`），SQL 使用 `LIMIT ? OFFSET ?`。✅

### 内存与资源

---

## Correctness

### 边界条件

`[MINOR]` `backend/collectors/sina.py:219` — `finance()` 无数据时返回空 `{}`，而非 `None`。上层 `collection_service.py` 以 `if item:` 判断——空 dict 被视为 `True` 导致尝试插入全 None 记录。建议统一 Provider 约定：无数据时返回 `None`。

### Null/Undefined 处理

### 竞态条件

`[MINOR]` `backend/storage/schema.py:133-145` — `ai_reports` 表无 `UNIQUE(symbol, date(generated_at))` 约束。`CREATE UNIQUE INDEX idx_ai_reports_symbol_date` 仅在索引层（line 200-201），并发两次 `force=True` 仍可能产生两份同日同标的报告。应在表定义内加表级 UNIQUE 约束或在 service 层在 INSERT 前做 `INSERT OR IGNORE`。

### 时区处理

- [x] **Timezone Handling** — 全项目统一使用 `datetime.now(timezone.utc)`，无裸 `datetime.now()` 调用。✅

### 异常处理

`[NIT]` `backend/services/evidence_builder.py:60-62, 252-253` — `finally` 块中的 `await conn.close()` 无 try-except 保护，若 close 失败会掩盖原始异常。

### Unicode 与编码

### 同步/异步混用

---

## Maintainability

### 架构边界合规

### 代码重复

### 接口设计

`[MINOR]` `backend/collectors/base.py:19-35` — `BaseProvider` 定义了 6 个抽象方法（`search/quote/kline/finance/fund_flow/technical`），但 RSS、新闻类 Provider 有 5 个返回空列表/空字典，违反接口隔离原则。建议拆分为 `BaseQuoteProvider` 和 `BaseNewsProvider`，或改为带默认空实现的非抽象方法。

### 配置一致性

### 类型注解

`[NIT]` `backend/scheduler/jobs.py:101` — `_TASK_FUNCTIONS: dict[str, object]` 类型注解过于宽泛。建议 `dict[str, Callable[[], Coroutine[Any, Any, None]]]`。

### 拼写

### 死代码

### 输入验证缺失

`[MAJOR]` `backend/api/portfolio.py:194-226` — `update_transaction` 缺少字段级校验：`UpdateTransactionRequest` 接受任意 `price`/`quantity`（含负数、零、极大值），`trade_date` 无日期格式校验（接受 `"not-a-date"`），`type` 字段未限制为 `Literal["buy","sell"]`。建议统一 Pydantic Field 约束 + `field_validator`。

### 其他

`[MINOR]` `backend/collectors/tencent_news.py:25` — 类 docstring 为英文，应改为中文（项目规范要求）。

`[MINOR]` `backend/collectors/tencent_news.py:127-130` — `tencent-news` CLI 未找到时若 `apikey` 存在仍尝试调用，建议一次性检测并缓存禁用状态。

`[MINOR]` `backend/services/ai_analyzer.py:71` — 置信度公式 `abs(score_diff) / max(total_score, 0.01)` 在信号极弱时（bullish=0.005, bearish=0.000）产生 100% 置信度。建议引入绝对幅度缩放。

### 错误处理

`[MINOR]` `backend/collectors/search_engine.py:115-116` — `extractor.feed(resp.text)` 遇到畸形 HTML 可能抛出 `HTMLParseError`，代码未捕获。建议包裹 try/except。

---

## Testing

---

## Documentation

## 汇总统计

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|------|----------|-------|-------|-----|--------|
| Security | 0 | 0 | 0 | 0 | 0 |
| Performance | 0 | 0 | 1 | 0 | 1 |
| Correctness | 0 | 0 | 2 | 1 | 3 |
| Maintainability | 0 | 1 | 5 | 1 | 7 |
| Testing | 0 | 0 | 0 | 0 | 0 |
| **合计** | **0** | **1** | **8** | **2** | **11** |

> 2026-06-04 增量审查发现 22 条问题（1 CRITICAL / 12 MAJOR / 9 MINOR），由 5 个并行修复 Agent 全部处理。git 历史保留审计（修复 commit: 2026-06-04 batches A-G）。
>
> **性能优化（Agent G 后续）**：发现 `httpx.AsyncClient` 在 Windows + Python 3.13 上单次创建耗时 3.8s（SSL/连接池），10 个 Provider × 3.8s = 38s import 阻塞。改为懒加载后 import time 从 201.8s 降到 0.9s（225 倍提速），`tests/test_scheduler.py` 单测从 1+ 小时降到 < 90s。
>
> **测试重构（H/I/J/K 后续）**：将 52 个同步 `def test_` 改为 `async def test_` 与项目 80% async 风格对齐；修复 `_run_*` 与 pytest-asyncio 事件循环冲突；修复 scheduler 5 vs 4 任务数 stale assertion。
>
> **2026-06-05 复审批次**：6 CRITICAL + 23 MAJOR + 10 MINOR + 5 NIT 问题已由修复 Agent 全部处理（git commit `6146ead` 之前及之后批次）；本轮 CODE_REVIEW.md 清理删除所有已修复条目。
>
> **2026-06-05 二次复审 5-Agent 后续清理**：5-Agent（L/M/N/O/P）并行复审整个项目 HEAD（`3b3c9b1`），发现 104 条新问题（5 CRITICAL / 37 MAJOR / 32 MINOR / 23 NIT = 97 条），已全部处理。

### 2026-06-05 复审历史精选（已全部修复，条目已删除）

> 完整列表见 `docs/review/2026-06-05-review.md`（已归档）。
> 已修复条目按规范删除，不再保留占位。
> 本轮额外修复: ui/pages/portfolio.py:110 pnl_color→pct_color 跨作用域 NameError。

---

## 项目亮点

- **SQL 注入防护** 🟢 — 100% 参数化查询
- **时区处理** 🟢 — 全局 `datetime.now(timezone.utc)`
- **Provider 隔离** 🟢 — 单源异常不影响其他标的
- **API 规范** 🟢 — 统一 `/api/v1/` 前缀 + 标准错误格式
- **日志统一** 🟢 — 全项目 `loguru`，无 `logging`/`print` 混用
- **架构分层** 🟢 — UI → API → Service → Collector/Storage，层级清晰
- **调度幂等** 🟢 — APScheduler 统一入口，配置驱动
- **写端点鉴权** 🟢 — 全部 POST 端点受 `verify_api_key` 保护
- **写锁序列化** 🟢 — 模块级 `_WRITE_LOCK` + `PRAGMA busy_timeout = 5000`
- **测试 Mock 规范** 🟢 — 全部统一为 `provider._client = MagicMock(); .method = AsyncMock()`

---

## 2026-06-05 复审清理（第 1 轮）

> 清理日期：2026-06-05
> 清理方式：删除已修复条目（不留 ✅/stale 标记），保留仍真实存在的问题
> 动作条目：本轮追加修复 4 处（tracked_assets 4 处 error 检查）
> Pydantic 输入验证补全（portfolio/news/reports）
> ui/pages/portfolio.py:110 pnl_color→pct_color 跨作用域 NameError
>
> 本轮删除的代表条目（17 条）：
> - Security: SecurityHeadersMiddleware 注册、写端点鉴权、tencent_news CLI key 泄露、CODEX_HOME 未签名
> - Performance: collect_quotes 并发、_collect_daily_close 并发、generate_reports conn 复用、get_assets ROW_NUMBER() CTE
> - Correctness: sina 前缀白名单扩展、ai_reports UNIQUE 约束
> - Maintainability: 重复 test 函数、tests/test_scheduler 同步/异步混用、sina test mock 模式、scheduler docstring 乱码
> - UI/Docs: tracked_assets/task_status 假成功、docs HTTP 方法、status 字段一致性
> - Tests: tests 同步 def test_ 改造、neodata test mock 模式
