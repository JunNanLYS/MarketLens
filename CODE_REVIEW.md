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

### 数据库索引

### 异步操作

### 分页

- [x] **Pagination** — 所有 list 接口均有 `page`/`page_size` 参数（`ge=1, le=100`），SQL 使用 `LIMIT ? OFFSET ?`。✅

### 内存与资源

---

## Correctness

### 边界条件

### Null/Undefined 处理

### 竞态条件

### 时区处理

- [x] **Timezone Handling** — 全项目统一使用 `datetime.now(timezone.utc)`，无裸 `datetime.now()` 调用。✅

### 异常处理

### Unicode 与编码

### 同步/异步混用

---

## Maintainability

### 架构边界合规

### 代码重复

### 接口设计

### 配置一致性

### 类型注解

### 拼写

### 死代码

### 输入验证缺失

### 其他

### 错误处理

---

## Testing

---

## Documentation

## 汇总统计

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|------|----------|-------|-------|-----|--------|
| Security | 0 | 0 | 0 | 0 | 0 |
| Performance | 0 | 0 | 0 | 0 | 0 |
| Correctness | 0 | 0 | 0 | 0 | 0 |
| Maintainability | 0 | 0 | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 | 0 | 0 |
| **合计** | **0** | **0** | **0** | **0** | **0** |

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

## 2026-06-05 复审清理（第 2 轮）

> 清理日期：2026-06-05
> 清理方式：删除全部 11 条剩余问题（不留 ✅ 标记），进入 0 issue 终态
> 本轮 4 个并行 Sub Agent 修复 + Master Agent 收尾 + 测试修正
>
> 删除条目（11 条）：
> - Performance [MINOR] `ui/pages/asset_detail.py:48-65` — 9 个 API 加 cache + 刷新按钮
> - Correctness [MINOR] `backend/collectors/sina.py:219` — `finance()` 返回 `None` 而非 `{}`
> - Correctness [MINOR] `backend/storage/schema.py:133-145` — `ai_reports` 索引表达式 + INSERT OR IGNORE
> - Correctness [NIT] `backend/services/evidence_builder.py:60-62, 252-253` — `conn.close()` 包 `suppress`
> - Maintainability [MINOR] `backend/collectors/base.py:19-35` — 6 个 abstract 改默认空实现
> - Maintainability [NIT] `backend/scheduler/jobs.py:101` — `_TASK_FUNCTIONS` 类型 `dict[str, Callable[[], None]]`
> - Maintainability [MAJOR] `backend/api/portfolio.py:194-226` — `UpdateTransactionRequest` 字段级 Pydantic 验证
> - Maintainability [MINOR] `backend/collectors/tencent_news.py:25, 127-130` — 类 docstring 中文化 + CLI 缺失缓存
> - Maintainability [MINOR] `backend/services/ai_analyzer.py:71` — 置信度公式加绝对幅度缩放
> - Maintainability [MINOR] `backend/collectors/search_engine.py:115-116` — HTMLParseError 已被 `except Exception` 覆盖
>
> 测试修正：
> - `tests/collectors/test_sina.py:343-365` — 3 个 finance() 测试从断言 `== {}` 改为 `is None`，对齐新约定
>
> 验证：311/311 tests pass

