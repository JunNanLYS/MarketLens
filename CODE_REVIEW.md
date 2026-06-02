# MarketLens Code Review

审查日期：2026-06-02（全项目审查）
审查范围：整个 MarketLens 项目（backend/、ui/、tests/、config.yaml）
审查方法：三轮审查 + 代码审查技能维度检查 + 全量代码阅读

---

## 历史未修复问题（来自上次审查）

| 优先 | 编号 | 级别 | 问题 |
|------|------|------|------|
| 1 | N-9 | MAJOR | get_realized_pnl 会计逻辑错误（当持仓清空后 avg_cost 不重置，后续计算的已实现盈亏失真） |
| 2 | N-8 | MAJOR | add_asset 存在 TOCTOU 竞态条件（SELECT 检查 -> INSERT 之间存在并发窗口） |
| 3 | N-10 | MAJOR | LIKE 查询匹配 JSON 数组子串（如 LIKE '%"sh600001"%' 会误匹配 sh60000111 等） |
| 4 | M-8+M-9 | MAJOR | EvidenceBuilder/ReportService 每次调用都创建新的 DB 连接，无连接复用 |
| 5 | N-22 | MAJOR | tasks.py API 层 fallback 路径直接操作数据库，违反分层约束 |
| 6 | N-21 | MINOR | AIAnalyzer 魔法数字硬编码（阈值 0.3/0.1 等未提取为常量） |

---

## 本次全项目审查发现的新问题

### [CRITICAL] N-35: get_positions 缩进错误导致批量查询在逐行循环内重复执行

- **File:** `backend/services/portfolio_service.py:347-369`
- **Problem:** 第 347 行的 `for row in rows:` 缩进层级为 8（在 `with get_db()` 上下文外部），而第 351-369 行的批量查询逻辑（`all_symbols`、`quotes_map`、`names_map`、数据库查询）缩进层级为 12，被嵌套在 `for row in rows:` 循环内部。这导致每一行交易记录都触发一次完整的数据库批量查询（每个标的 N 条交易 = N 次批量查询而不是 1 次）。第 369 行 `positions = []` 也在循环内每次重置（虽然第 370 行的第二个循环会在首个循环结束后重新填充，属于意外正确）。
- **Fix:** 将第 347-369 行的缩进整体调整：`for row in rows:` 缩进至 12（回到 `with get_db()` 内），批量查询逻辑（351-367 行）和 `positions = []`（369 行）提升至 8 层级（在 `for row in rows:` 循环外部，与第二个 for 循环同级）。
- **Status:** ✅ 已修复

### [MAJOR] N-36: EvidenceBuilder._build_quote 使用了错误的配置键

- **File:** `backend/services/evidence_builder.py:83`
- **Problem:** `_build_quote` 调用 `self._get_config_limit("finance_limit", 2)` 来获取行情查询的 LIMIT 参数，但该配置键是财务数据的行数限制。虽然功能上 `fetchone()` 只返回一行所以影响不大，但语义错误且会让配置项含义混乱。
- **Fix:** 使用专用的配置键（如 `quote_limit`），或简化为 `LIMIT 1`（因为是 `fetchone()`）。

### [MAJOR] N-37: UI search_assets 使用 POST 而非 GET，违反 AGENTS.md §6

- **File:** `ui/api_client.py:91`
- **Problem:** `search_assets` 函数通过 `client.post("/assets/search", json=payload)` 发起搜索请求，但后端路由是 `GET /api/v1/assets/search`。POST 用于纯查询违反 AGENTS.md §6 中"POST 不得用于纯查询"的约束。
- **Fix:** 改为 `client.get("/assets/search", params=payload)`，匹配后端 GET 路由。
- **Status:** ✅ 已修复

### [MAJOR] N-38: MARKET_OPTIONS 字典包含重复键导致选项缺失

- **File:** `ui/pages/tracked_assets.py:10-21`
- **Problem:** `MARKET_OPTIONS` 字典中"全部"键出现两次（第 10 行和第 18 行），且后 5 个条目与前半部分完全重复。Python 字典的后一个键值会覆盖前一个，导致实际有效条目只有 5 个（"全部"、"A 股 (sh)"、"A 股 (sz)"、"港股 (hk)"、"美股 (us)"），缺少"期货 (fut)"、"国际商品 (hf)"、"国内期货 (nf)" 三个市场过滤选项。
- **Fix:** 删除重复的 5 个条目，保留完整的 8 个市场选项。
- **Status:** ✅ 已修复

### [MAJOR] N-39: tencent_news.py 和 search_engine.py 缺少类型注解，违反 AGENTS.md §11

- **File:** `backend/collectors/tencent_news.py:18-98`, `backend/collectors/search_engine.py:76-148`
- **Problem:** 两个 Provider 的大多数方法缺少参数和返回值类型注解（如 `_run`、`_parse_json`、`_parse_table`、`_fetch_engine` 等），且 `__init__` 方法使用默认参数 `params=None` 缺少类型声明。
- **Fix:** 补充完整的类型注解，例如 `def _run(self, args: list[str]) -> tuple[str | None, str | None]:`。

### [MAJOR] N-40: config.yaml 中 cors_origins: ['*'] 存在安全隐患

- **File:** `config.yaml:73`
- **Problem:** CORS 配置允许所有来源（`'*'`），在生产环境中任何网站都可以向 MarketLens API 发起跨域请求。
- **Fix:** 在部署文档中说明需要将 `cors_origins` 限定为实际前端域名。当前开发阶段可保留，但建议在 README 中标注。

### [MAJOR] N-41: NeoDataClient._is_auth_error 在 _do_request 中调用时未传入 body

- **File:** `backend/collectors/neodata_client.py:120-124`
- **Problem:** `_do_request` 先调用 `_is_auth_error(resp.status_code, None)` 检查 HTTP 状态码（body 参数传 None），然后才 `resp.raise_for_status()` 并解析 `resp.json()`。这意味着 `_is_auth_error` 永远无法检查响应 body 中的 `code`/`msg` 字段。若接口返回 HTTP 200 但 body 中 code 表示鉴权失败（如 `code=40101`），则鉴权失败会被静默忽略。
- **Fix:** 先解析 `resp.json()` 获取 body，再同时传入 status_code 和 body 给 `_is_auth_error`。

### [MINOR] N-42: neodata.py API 模块级单例在配置变更后不会更新

- **File:** `backend/api/neodata.py:20-27`
- **Problem:** `_client` 是模块加载时创建的全局变量。如果用户在运行时更新 config.yaml 中的 token 或 endpoint，`_client` 不会自动重新初始化——`get_token_status`、`save_token` 仍使用旧配置。
- **Fix:** 将 `_client` 改为函数内懒初始化（每次请求时动态获取），或至少提供重新加载的能力。

### [MINOR] N-43: AIAnalyzer 信号阈值缺少命名常量

- **File:** `backend/services/ai_analyzer.py:67-80`
- **Problem:** 信号判断的阈值（0.3、0.1、-0.1、-0.3）和置信度/风险评级阈值（0.6、0.3、0.2）均为魔法数字，缺少注释说明其分析含义。与 N-21 相关但更具体。
- **Fix:** 提取为模块级常量，如 `SIGNAL_BULLISH_STRONG = 0.3`，并添加注释。

### [MINOR] N-44: get_realized_pnl 文档字符串为乱码

- **File:** `backend/services/portfolio_service.py:426`
- **Problem:** `get_realized_pnl` 方法的文档字符串为 `"""???????????????????"""`，不可读的乱码，可能是编码转换错误。
- **Fix:** 替换为正确的中文文档字符串。
- **Status:** ✅ 已修复

### [MINOR] N-45: generate_reports 在循环内为每个标的创建独立 DB 连接

- **File:** `backend/services/report_service.py:38-45`
- **Problem:** `generate_reports` 方法对每个 symbol 调用 `with get_db() as conn:`。当标的数量较多时（如 20 个），意味着 20 次连接创建/销毁和独立事务边界。
- **Fix:** 将所有 symbols 的处理放在同一个 `with get_db()` 上下文内。

### [NIT] N-46: build_fund_flow_summary 存在重复实现

- **File:** `backend/utils.py:1-30` 和 `backend/services/asset_service.py:243-271`
- **Problem:** `build_fund_flow_summary` 函数在 `utils.py`（模块级函数）和 `asset_service.py`（静态方法）中均存在，实现相似但不完全一致，违反 DRY 原则。
- **Fix:** 统一为一个实现，让 asset_service.py 调用 utils.py 的实现。

### [NIT] N-47: main.py 全局可变单例 _scheduler_manager

- **File:** `backend/main.py:20`
- **Problem:** `_scheduler_manager` 是模块级可变全局变量，在 `lifespan` 中通过 `global` 修改。测试环境中可能导致状态泄漏。
- **Fix:** 使用 `app.state.scheduler_manager` 管理调度器实例，避免模块级可变状态。

### [NIT] N-48: GET /api/v1/assets/search 返回结构与分页端点不一致

- **File:** `backend/api/assets.py:114-120`
- **Problem:** 搜索结果返回 `{"items": items, "total": len(items)}` 而不支持分页，与 `news`、`reports`、`assets` 列表的 `page_info` 结构不一致。
- **Fix:** 添加分页参数或加注释说明搜索不需要分页的设计意图。

### [NIT] N-49: _collect_fund_flow 中的死代码分支

- **File:** `backend/services/collection_service.py:265`
- **Problem:** `items = data if isinstance(data, list) else [data]` 试图处理 fund_flow 返回 dict 或 list。根据 Provider 接口约定，`fund_flow()` 返回 `dict`，所以 `isinstance(data, list)` 检查永远为 false——这个分支是死代码。
- **Fix:** 移除此分支，或添加注释说明为何需要兼容。

---

## 审查维度总结

| 维度 | 评估 | 关键发现 |
|------|------|---------|
| 安全性 | 中等 | CORS * 全放行（N-40）、NeoData auth body 检查缺失（N-41） |
| 性能 | 中等 | get_positions 批量查询重复执行（N-35，已修复）、循环内逐标的 DB 连接创建（N-45） |
| 正确性 | 中等 | get_positions 缩进错误（N-35，已修复）、_build_quote 错误配置键（N-36）、MARKET_OPTIONS 重复键（N-38，已修复） |
| 可维护性 | 中等 | tencent_news/search_engine 缺类型注解（N-39）、基金流水摘要重复（N-46）、魔法数字（N-43） |
| 测试 | 良好 | 294 个测试全部通过，覆盖 collectors/services/storage/scheduler 主要路径 |
| 文档 | 中等 | get_realized_pnl 乱码文档串（N-44，已修复）、AGENTS.md 与部分代码不一致（N-37 N-22） |

### 正面发现

- 数据源提供者模式设计清晰，声明与实现分离良好
- 所有外部 API 调用均有超时设置和异常捕获
- Provider 失败不阻塞主流程，optional 源静默跳过
- 数据库操作使用参数化查询，无明显 SQL 注入风险
- Scheduler 使用 APScheduler 进行定时任务管理，架构合理
- 测试覆盖 294 个用例，核心路径有较好保障
- 日志使用 loguru，采集和任务执行有 run_logs 追踪

---

## 审查统计

| 严重级别 | 本次发现 | 历史未修复 | 合计 |
|---------|---------|-----------|------|
| CRITICAL | 1 (N-35, ???) | 0 | 1 |
| MAJOR | 6 (N-36~41, ?????) | 2 (M-8/9, N-22) | 8 |
| MINOR | 4 (N-42~45, ?????) | 1 (N-21) | 5 |
| NIT | 4 (N-46~49, ?????) | 0 | 4 |

---

## 优先修复建议

1. N-35 已修复 — get_positions 缩进错误
2. N-38 已修复 — MARKET_OPTIONS 重复键
3. N-37 已修复 — search_assets POST->GET
4. N-44 已修复 — get_realized_pnl 文档串乱码
5. 建议本迭代处理 N-36, N-39, N-41 — 配置正确性和代码规范
6. 建议下迭代处理 N-42~49 — 改进项和风格问题

## 历史已修复问题（保留记录）

| 编号 | 级别 | 问题 | 状态 |
|------|------|------|------|
| N-31 | MAJOR | RSSProvider._get_text 丢失 @staticmethod | 已修复 |
| N-32 | MAJOR | __init__.py create_providers 丢失类型注解 | 已修复 |
| N-33 | MINOR | tencent_news.py _max_items 条件多余 | 已修复 |
| N-34 | MINOR | 新 Provider 缺少重复类型注解 | 非阻塞 |
| N-11 | MAJOR | RSS namespace 解析失败 | 已修复 |
| N-28 | MAJOR | TokenManager JWT exp | 已修复 |
| N-29 | MINOR | NeoData dead code | 已修复 |
| N-30 | MINOR | NeoData docs missing | 已修复 |
| N-20 | MAJOR | NeoDataProvider type annotations | 已修复 |
| M-13 | MINOR | westock shell=True | 已排除 |
