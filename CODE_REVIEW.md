# MarketLens Code Review

> 审查日期：2026-06-05 | 审查范围：整个项目（HEAD）| 审查方式：4-Agent 并行深度复审
> 维度：Correctness / 数据完整性+采集可靠性 / 性能+可维护性 / UI+可访问性+集成边界
>
> **威胁模型**：MarketLens 是单用户本地工具（详见 `CLAUDE.md` "Project context"）。Security 维度的通用清单（CORS/CSRF/时序攻击/外部 feed 注入）已被 `CLAUDE.md` 明确**不视为安全问题**。

## 汇总统计

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|------|----------|-------|-------|-----|------|
| Correctness | 5 | 1 | 2 | 1 | 9 |
| 数据完整性 + 采集可靠性 | 2 | 4 | 3 | 3 | 12 |
| 性能 + 可维护性 | 0 | 4 | 7 | 4 | 15 |
| UI + 可访问性 + 集成边界 | 0 | 3 | 7 | 2 | 12 |
| **合计** | **7** | **12** | **19** | **10** | **48** |

> 4-Agent 并行审查共发现约 60 条候选问题，已去重并按 CLAUDE.md 优先级排序。**本表只保留经多 Agent 交叉验证的高置信度问题**。NIT/MINOR 仅列出有明确修复价值的；纯风格偏好不计入。

---

## Correctness（最高优先级 — 资金/时区/边界/并发）

### [CRITICAL] `portfolio_service.py:347-399, 432-446` — `update_transaction` / `delete_transaction` race condition（写锁绕过）

**问题**:
- `update_transaction` 用 `get_connection_sync()` 直接拿连接，**不持有 `_WRITE_LOCK`**
- `delete_transaction` 同样的裸连接模式 + soft-delete 后回查 + UPDATE 恢复，两个 UPDATE 都在 auto-commit 路径
- Streamlit rerun 期间用户快速编辑同一标的的 sell 交易，可同时通过 post-check

**影响**: 同一 `(account_id, symbol)` 的并发 PATCH 可绕过 WAC 校验产生负持仓。**这是项目最严重的资金正确性 bug**。

**修复**:
1. 加 `_WRITE_LOCK` 包裹整段 read-update-recheck-commit
2. 或用单条 CTE-原子 SQL：`UPDATE ... WHERE (SELECT ...) >= 0`
3. 与 `create_transaction` 保持一致的 `with get_db() as conn` 风格

### [CRITICAL] `portfolio_service.py:228-233` — `split` 类型 quantity 写时无校验

**问题**: `total_qty *= row["quantity"]` 处理 split 时，`quantity=0` → 持仓变 0；`quantity<0`（反向拆股符号错）→ 持仓变负。**API 层 Pydantic 接受 `quantity > 0` 但不区分 split vs buy 的语义**。

**修复**: 写时校验 `split` 类型 `quantity > 0` 且为合理 ratio（建议 `le=1000`）；在 service 层强制，不依赖 API 层。

### [CRITICAL] `portfolio_service.py:235-251` — WAC 误算：首笔为 sell 时产生"幻股"

**问题**: 当第一笔交易是 sell（无前置 buy 记录）时，WAC 累加器将 `quantity` 减为负值，且 `avg_cost` 计算公式 `total_cost / total_qty` 在 total_qty 为负时得到**负 avg_cost**，污染后续所有 P&L 计算。

**修复**: 首笔为 sell 时直接拒绝（"在 sell 之前必须先 buy"）；或在累加器中用绝对值分离 buy/sell。

### [CRITICAL] `portfolio_service.py:470-495` — `get_positions` 长持有连接 + post-commit 迭代看到陈旧数据

**问题**: `get_db()` 上下文管理器退出 commit 后，代码继续在 Python 端迭代 `quote_rows`，此时别的写入可能已改变行情。P&L 显示的是过期价格 + 当前 cost basis。

**修复**: 在 `with get_db() as conn` 块内完成所有 row 拼接；将 dict 化放在锁内；context 退出后只读取内存中的不可变数据。

### [CRITICAL] `portfolio_service.py:575-583` — WAC 计算忽略买入手续费

**问题**: 买入时 `total_cost += price * quantity`，**手续费被忽略**。手续费从 `fee` 列读取后仅在已实现 P&L 卖出时扣减；买入时未摊入成本基础 → **买入手续费"消失"**，长期持有多笔买入时 `avg_cost` 偏低、P&L 虚高。

**修复**: 买入累计 `total_cost += (price * quantity + fee)`，并在卖出时按比例摊回。

### [MAJOR] `portfolio_service.py:487` — `market_quotes` 相关子查询在 MAX 冲突时返回多行

**问题**: `WHERE collected_at = (SELECT MAX(collected_at) FROM market_quotes WHERE symbol = mq.symbol)` 在两个同毫秒采集行时返回 2 行，导致 `quotes_map` 中同一 symbol 重复项；`get_positions` 可能重复累加。

**修复**: 改用 CTE + `ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY collected_at DESC)` 取 rn=1。

### [MAJOR] `scheduler/jobs.py:31, 80` — 启动健康检查用 naive `datetime.now()`

**问题**: `_check_neo_data_token_on_startup` 用 `datetime.now().isoformat()`（本地 naive），与服务层 `datetime.now(timezone.utc).isoformat()` 不一致。`run_logs.started_at`/`finished_at` 比较时混用 UTC 和本地时区，**可能产生负 duration**。

**修复**: 全部统一 `datetime.now(timezone.utc)`。

### [MINOR] `portfolio_service.py:585-586` — split 分支未调整 `avg_cost`

**问题**: 拆股只乘 `total_qty`，`avg_cost` 保持不变（拆股后每股成本应按比例下降，否则 implied P&L 虚高）。典型场景：100 @ 380 → 拆 2:1 后持仓 200 @ 380（应为 200 @ 190）。

**修复**: 拆股时同步 `avg_cost = avg_cost / split_ratio`。

### [MINOR] `api/portfolio.py:201-203` — `date_from`/`date_to` 未校验 ISO 格式

**问题**: 端点接收 `str | None` 的 date filter，原样拼入 SQL（参数化所以无注入），但格式错误时 SQL 比较按字符串字典序工作（恰好 YYYY-MM-DD 排序正确），坏数据静默通过。

**修复**: 用 `datetime.date` 类型 + Pydantic 解析，或在 service 入口调用现有 `_validate_trade_date` helper。

### [NIT] `portfolio_service.py:677-686` — `_compute_avg_cost` 死代码

**问题**: 方法定义但未调用，与 `_compute_position_detail` 重复。可删除。

---

## 数据完整性 + 采集可靠性

### [CRITICAL] `news_service.py:57-151` — 新闻采集写端点绕过 `_WRITE_LOCK`

**问题**: 整个 INSERT 块（news_items + raw_data + run_logs）`with get_db() as conn` 没有 `_WRITE_LOCK`。CLAUDE.md 硬约束 "writes MUST hold `_WRITE_LOCK`"。60min 调度周期内，scheduler tick 与 API 写请求重叠时可触发 `OperationalError: database is locked`。

**修复**: 在第二个 `with get_db() as conn` 块外层加 `with _WRITE_LOCK:`。

### [CRITICAL] `scheduler/jobs.py:171-182` — `_run_cleanup` DELETE 同样绕过 `_WRITE_LOCK`

**问题**: 03:30 定时清理 `raw_data` 时，若与 `quote`/`daily_close` scheduler tick 重叠，5s busy_timeout 后可能 OperationalError。

**修复**: 同样加 `_WRITE_LOCK` 包裹。

### [MAJOR] `news_service.py:105` — News INSERT 不带 `OR IGNORE`

**问题**: 依赖 Python 端 `existing_urls` 集合（5000 行 LIMIT）做去重；URL 为空字符串或 NULL 时绕过 unique index partial condition，**每次 tick 都插入新行**。同源新闻在两个 provider 同时返回时被 broad `except Exception` 吞掉，错误日志是"新闻入库失败"而非"已存在"。

**修复**: 改为 `INSERT OR IGNORE INTO news_items (...)`，把 unique index 作为最终安全网；Python 端 set 退化为预过滤优化。

### [MAJOR] `news_service.py:67-72` — 5000 行 URL 预取窗口之外的新闻会重复入库

**问题**: 5000 行 LIMIT 假定"最新 5000 行覆盖所有近期 URL"。老文章被重新发布、URL 出现在第 5001+ 行时，dedup 漏检。`run_logs` 出现"0 new"假阳性。

**修复**: 同上，靠 `INSERT OR IGNORE` 兜底；或扩大 LIMIT 并分页。

### [MAJOR] `report_service.py:66-71` — `_get_active_symbols` 抛错时 `run_logs` 不写

**问题**: 若 `_get_active_symbols()` 抛异常，外层 `try/except` 在写 run_logs 之前就返回，导致任务失败无审计记录。

**修复**: 把 `run_logs` 写入移到 `_get_active_symbols` 之前/外层；用 `try/finally` 保证 run_logs 一定写。

### [MAJOR] `collectors/westock.py:62-75` — `_detect_error` 错误信息不可读

**问题**: 正则匹配触发短语后 `return m.group(0).strip()`，**只回显触发短语**（如"查询行情失败"），无实际原因。`run_logs.error_message` 全是"查询行情失败 : "，调试时无信息。

**修复**: 用固定错误码常量（如 `WESTOCK_QUERY_FAILED`）作为返回值，匹配文本作 context 追加；不要整段当 error_message。

### [MINOR] `collectors/westock.py:104-126` — `subprocess.run` 不传 `env=`

**问题**: 默认继承父进程完整 env。若用户有不同 `npx` 在 PATH 上，版本可能漂移。

**修复**: 在 provider init 用 `shutil.which` 解析绝对路径，启动时传 `env={"PATH": parent_dir}` 最小化 env。

### [MINOR] `collectors/tencent_news.py:78-87` — 连续超时未 disable provider

**问题**: 现有 `_cli_disabled` 只在 CLI 缺失时触发；连续 3 次 TimeoutError 仍每次重试。

**修复**: 加 `_consecutive_timeouts` 计数器，N=3 后 disable。

### [MINOR] `services/news_service.py:132` — `raw_data.symbol = "news"` 占位符

**问题**: 全局新闻存 `symbol="news"`，污染 `idx_raw_data_symbol_type` 索引，审计时过滤易混。

**修复**: `symbol` 改为可空 NULL，单标的相关新闻存真实 symbol，全局新闻 symbol 留 NULL。

### [NIT] `services/portfolio_service.py:643-654` — `IN (?, ?), (?, ?)` 元组 IN 不走索引

**问题**: SQLite 不会把 tuple-in-list 解包为 row-value expression，planner 退化为全表扫。

**修复**: 改用 `WHERE (account_id, symbol) IN (VALUES (?,?), (?,?), ...)` 或 `WHERE account_id IN (...) AND symbol IN (...)` 加客户端交叉验证。

---

## 性能 + 可维护性

### [MAJOR] `services/asset_service.py:307-343` — `get_asset_by_id` CTE 产生 60×5=300 行笛卡尔积

**问题**: `LEFT JOIN klines k ON ... AND k.rn <= 60 LEFT JOIN flows f ON ... AND f.rn <= 5` 无显式 join predicate，产生 300 行。Python 端循环再按 `IS NULL` 过滤 295 行。**每次详情页加载都触发**。

**修复**: 拆为两个独立查询（kline 60 行 + flow 5 行），或拆 CTE。代码注释中已说"分两个查询更清晰"但没落地。

### [MAJOR] `ui/pages/portfolio.py:46, 115` — `get_positions()` / `get_realized_pnl()` 缺 `@st.cache_data`

**问题**: 每次 Streamlit rerun（包括输入框焦点变化）都重新拉取，每次跑聚合查询。

**修复**: 加 `@st.cache_data(ttl=15)` module-level helper 包装，与 `_fetch_accounts` 一致。

### [MAJOR] `services/collection_service.py:223-450` — `_fetch_kline/_fetch_finance/_fetch_fund_flow/_fetch_technical` 4-way 重复

**问题**: 4 套结构相同的 `_fetch_*` + 4 套 `_insert_*`，共 200+ 行近重复代码。添加第 5 类数据需 copy-paste 两组方法。

**修复**: 抽 `_run_provider_iteration(call_fn, data_type, build_row_fn)` + dispatch dict `{"kline": (provider.kline, build_kline_row), ...}`。

### [MAJOR] `collectors/westock.py:18, 50, 75, 380-388` — 硬编码 market prefix 不在 config 中

**问题**: `("sh", "sz", "bj", "hk", "us", "hf", "nf", "gb")` 在 sina/westock 4 处硬编码，加新市场需改 4 个地方。违反 CLAUDE.md "声明与实现分离"。

**修复**: 在 `data_sources.sina.prefixes` 等 config 段声明，初始化时一次性读取。

### [MINOR] `collectors/base.py:28-50` — 6 abstract 方法在 news-only provider 中产生 boilerplate

**问题**: RSS / SearchEngine / TencentNews 5 个未实现方法各写 `return []` 一次，5×7=35 行 boilerplate。

**修复**: 拆 `StructuredProvider` + `NewsProvider` 两个 ABC；news provider 只继承 `NewsProvider`。

### [MINOR] `services/evidence_builder.py:144-167` — `build_multi` 拉 5000 行新闻再 Python 端过滤

**问题**: `LIMIT 5000` 拉全表新闻，Python 端遍历 `related_symbols` JSON 字段分类；批量 AI 报告生成时这是热点。

**修复**: 用 `SELECT n.* FROM news_items n, json_each(n.related_symbols) j WHERE j.value IN (?, ?, ...)` 在 SQL 层过滤。

### [MINOR] `services/news_service.py:204-217` — `_tag_patterns_cache` 用 `id(row)` 做 key 无效

**问题**: `sqlite3.Row` 的 `id()` 在 fetchall 后被 GC 回收，缓存实际从不命中。Dead code。

**修复**: 删除缓存或改用 `(symbol, tags_str)` 稳定 key。

### [MINOR] `services/portfolio_service.py:486-490` — `quotes_map` 用相关子查询

**问题**: 50 标的 = 50 个子查询。已有 `get_asset_by_id` 的 ROW_NUMBER 模式可复用。

**修复**: 改 CTE + ROW_NUMBER。

### [MINOR] `services/collection_service.py:94-125` — `_collect_quote_for_symbol` 锁粒度可优化

**问题**: 单标的 insert 也开/关连接 + 锁一次。100 标的 × 开/关 = 100 次 SQLite 同步 I/O。

**修复**: 参照 `_collect_daily_close_for_symbol` 的 fetch → 批量 commit 两阶段模式。

### [MINOR] `services/asset_service.py:197-212` — `get_assets` CTE 全表扫 `market_quotes`

**问题**: `ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY collected_at DESC)` 对全表做窗口排序。100 标的 × 15min 周期 = 3.5M 行/年。

**修复**: 已存在 `UNIQUE(symbol, collected_at)` 索引；考虑加 `(symbol, collected_at DESC)` 优化 loose-index-scan。

### [NIT] `collectors/tencent_news.py:116, 134, 139, 148` — 中文用 `\u` 转义

**问题**: `腾讯新闻` 应该是"腾讯新闻"字面量。违反 CLAUDE.md 中文注释/docstring 规则（推广到可读性）。

**修复**: 替换为字面中文。

### [NIT] `collectors/*/base.py` — `_get_client`/`close` 在 4 个 provider 重复 13 行

**问题**: lazy httpx client 模板代码 4× 重复 52 行。

**修复**: 抽 `_LazyClientMixin` 到 `base.py`。

### [NIT] `services/portfolio_service.py:677-686` — `_compute_avg_cost` 死代码

**问题**: 未被调用。

**修复**: 删除。

### [NIT] `collectors/westock.py` CLI 路径解析

**问题**: 见 MINOR #6，附加 NIT：CLI 路径在 `__init__` 时不解析，启动后 PATH 变化不感知。

---

## UI + 可访问性 + 集成边界

### [MAJOR] `docs/api/neodata.md:24-37` vs `backend/api/neodata.py:71-76` — `/token-status` 字段名错

**问题**: 文档写 `has_token` / `expires_at`；代码返回 `is_valid`，**无 expires_at**。用户按文档实现客户端会 KeyError。

**修复**: 文档改为 `{"is_valid": true, "source": "cache"}`。

### [MAJOR] `docs/api/assets.md:207` vs `backend/api/assets.py:20-24` — PATCH `/assets` 字段名错

**问题**: 文档说 `name` 可更新；`AssetUpdateRequest` 只接受 `enabled/tags/notes`。用户按文档改名得到 422 或静默丢失。

**修复**: 文档删除 `name` 字段或 model 加 `name`。

### [MAJOR] `ui/pages/task_status.py:64` — `running` 过滤永远不匹配

**问题**: Selectbox 提供 `["全部", "success", "failed", "running"]`，但 `run_logs.status` 实际只写 `success` / `failure`。选 `running` 得到空列表。

**修复**: 移除 `running` 选项；或在任务开始时持久化 `running` 状态、结束 update。

### [MINOR] `ui/pages/settings.py:8-25` — `ui/` 直接读 `config.yaml` 违反层边界

**问题**: 用 `open(Path(__file__).parents[2] / "config.yaml")` 解析 YAML。代码自承认"临时直读，后续应新增 GET 端点"。CLAUDE.md 明确禁止 ui 直读 config。

**修复**: 新增 `GET /api/v1/config/data-sources`，UI 改调 API。

### [MINOR] `ui/pages/portfolio.py`, `tracked_assets.py`, `asset_detail.py`, `task_status.py`, `ai_reports.py` — P&L 颜色盲不可达

**问题**: 多处用 `:green[...]` / `:red[...]` 单色信号盈亏，~8% 男性色盲无法区分。AI 报告的 action 4 状态（buy/sell/watch/avoid）也只用颜色。

**修复**: 加 `▲` / `▼` 文本前缀或 icon，color 作为辅助信号。

### [MINOR] `ui/app.py:32` — 侧栏 radio `label_visibility="collapsed"` 隐藏标签

**问题**: 屏幕阅读器失去 "导航" 标签，无法识别是主导航控件。

**修复**: 改 `label_visibility="visible"` 或加 `aria-label`。

### [MINOR] `ui/pages/portfolio.py:220, 238, 306, 363, 422` — `st.cache_data.clear()` 全局清

**问题**: 每次单笔交易编辑后 `st.cache_data.clear()` 清空所有模块级缓存，包括详情页行情/新闻，造成 cold-cache 重新加载。

**修复**: 用 keyed invalidation 或 namespace 化 `@st.cache_data`。

### [MINOR] `backend/main.py:74-76` — `lifespan shutdown` 不关 provider clients

**问题**: 6 个 HTTP Provider 都有 `close()` 但 lifespan 关闭 scheduler 后不调它们。`httpx.AsyncClient.aclose()` 跳过 → Windows Proactor 偶发"Unclosed client"警告。

**修复**: lifespan shutdown 时遍历 `_get_collection_service()._providers` 调 `close()`。

### [MINOR] `docs/api/portfolio.md:253` — `/positions/realized-pnl` 分页 doc 过时

**问题**: 文档说"端点不暴露分页参数"；实际 `backend/api/portfolio.py:282-291` 已接受 `page`/`page_size`。

**修复**: 文档删除 "TODO 后续版本补充" 段。

### [NIT] `ui/pages/portfolio.py:28` — `_fetch_accounts` cache TTL 15s 偏短

**问题**: 账户列表几乎不变，30s+ 都行；与 `asset_detail` 的 30s 不一致。

**修复**: 改为 60s。

### [NIT] `ui/pages/ai_reports.py:110` — 手动生成按钮缺 `help=`

**问题**: `st.button("🔄 手动生成报告")` 无 help。

**修复**: 加 `help="立即为所有启用标的生成 AI 报告"`.

---

## 项目亮点

- **SQL 注入防护** 🟢 — 100% 参数化查询
- **时区处理** 🟢 — 全局 `datetime.now(timezone.utc)`（除 jobs.py:31, 80 待修）
- **Provider 隔离** 🟢 — 单源异常不影响其他标的
- **API 规范** 🟢 — 统一 `/api/v1/` 前缀 + 标准错误格式
- **日志统一** 🟢 — 全项目 `loguru`，无 `logging`/`print` 混用
- **架构分层** 🟢 — UI → API → Service → Collector/Storage，层级清晰
- **调度幂等** 🟢 — APScheduler 统一入口，配置驱动
- **写端点鉴权** 🟢 — 全部 POST 端点受 `verify_api_key` 保护
- **写锁序列化** 🟢 — 模块级 `_WRITE_LOCK`（待 portfolio/news_service 接入）
- **测试 Mock 规范** 🟢 — 全部统一为 `provider._client = MagicMock(); .method = AsyncMock()`
- **HTTP 客户端懒加载** 🟢 — `httpx.AsyncClient` 全部在 `_get_client` 中创建
- **API 分页** 🟢 — 所有 list 接口均有 `page`/`page_size` 参数（`ge=1, le=100`）
- **Provider 优先链** 🟢 — config-driven，动态加载
- **测试覆盖广度** 🟢 — 335 个测试
- **Async 一致性** 🟢 — 全部 `_run_*` wrapper 正确处理 sync/async 边界

---

## 待修复清单（按优先级）

### 🔴 CRITICAL（7 项）
1. **持仓并发安全** — `_WRITE_LOCK` 序列化 portfolio `update_transaction` / `delete_transaction`
2. **新闻写锁** — `news_service.collect_news` 加 `_WRITE_LOCK`
3. **清理写锁** — `_run_cleanup` 加 `_WRITE_LOCK`
4. **split 类型写时校验** — service 层强制 `quantity > 0` 且为 ratio
5. **WAC 幻股** — 拒绝首笔为 sell 的持仓计算
6. **WAC 忽略买入手续费** — `total_cost += price*quantity + fee`
7. **`get_positions` 长连接 + post-commit 陈旧** — 所有 dict 化放入 `with` 块内

### 🟡 MAJOR（12 项）
8. **MAX 冲突子查询改 ROW_NUMBER** — `get_positions` quotes_map
9. **股票详情页 CTE 笛卡尔积** — `get_asset_by_id` 拆两个查询
10. **portfolio Streamlit 缓存** — `get_positions` / `get_realized_pnl` 加 `@st.cache_data(ttl=15)`
11. **4-way 重复 fetch/insert** — `collection_service` 抽 dispatch dict
12. **market prefix 硬编码** — 移入 config
13. **news INSERT OR IGNORE** — DB 层兜底去重
14. **5000 行 URL 预取窗口** — 依赖 UNIQUE INDEX
15. **report_service 失败时 run_logs 不写** — 外层 try/finally
16. **westock 错误信息不可读** — 用错误码
17. **jobs.py naive datetime** — 改 UTC
18. **`/token-status` 文档错** — `is_valid` 不是 `has_token`
19. **`PATCH /assets` 文档错** — 文档删 `name` 字段
20. **`running` 过滤** — 移除选项或持久化

### 🟢 MINOR / NIT
- 详见各维度清单

---

## 审查结论

**总体判断**: 项目架构清晰、SQL 注入防护到位、并发原语选型正确（threading.Lock for cross-loop）、懒加载实现完整。主要风险集中在**资金计算的精度和并发安全**——`portfolio_service` 的 `_WRITE_LOCK` 缺失和 split/手续费/幻股几个算法问题在单用户本地工具场景下**直接砸到用户的 P&L**。

**不会影响的维度（已通过威胁模型过滤）**:
- 通用 Security 清单（CORS/CSRF/feed 注入/时序攻击/默认 key）
- 多租户/水平扩展
- 生产部署相关（TLS/认证供应商/限流）

---

## 第 5 轮审查 — 2026-06-06

> 审查范围：4-Agent 并行审查（Correctness / 数据完整性+采集可靠性 / 性能+可维护性 / 证据链+AI+UI+集成）
> 输入：4 份 agent 报告共 54 条候选新发现，**已与已登记 48 条去重 + 同源合并**后保留 **28 条**入库
> 合并原则：同根因（如 `run_logs` 缺失、`raw_data` 占位符、`architecture.md` 文档漂移、`lifespan` 资源）合并为 1 条；不同面（性能 vs 可维护性）保留为不同条目
> 已知遗留（CLAUDE.md "Known issues" 4 条 ✅ 已解决项）不复查

### 新发现汇总

| 维度 | CRITICAL | MAJOR | MINOR | NIT | 合计 |
|------|----------|-------|-------|-----|------|
| Correctness | 2 | 3 | 0 | 0 | 5 |
| 数据完整性 + 采集可靠性 | 1 | 5 | 2 | 0 | 8 |
| 性能 + 可维护性 | 1 | 3 | 1 | 2 | 7 |
| 证据链 + AI + UI + 集成 | 0 | 0 | 4 | 1 | 5 |
| **合计** | **4** | **11** | **7** | **3** | **25** |

> 维度归属说明：Agent D 报告 9 条新发现（evidence_builder / ai_analyzer / asset_service.latest_report / UI 4 域 tab 缺失 / docs 漂移 / lifespan），按"代码所在层"拆入前 3 个维度。

### 已登记 48 条状态复验

| 状态 | 数量 | 说明 |
|------|------|------|
| 已修复 | 6 | `news_service` 写锁 / `_run_cleanup` 写锁 / `portfolio_service` split 校验 / WAC buy fee / `get_positions` 锁内 dict 化 / `scheduler/jobs.py` naive datetime |
| 部分修复 | 2 | 首笔为 sell 拒绝（create 已修，update 路径残留理论窗口）/ P&L 颜色盲（ai_reports 加了 emoji，但 portfolio.py / asset_detail.py 仍纯红绿） |
| 未修复 | 40 | 待修复清单全部保留（按原优先级） |

> **复验结论**：第 5 轮是新功能叠加（chip/margintrade/blocktrade/lhb/calendar/etf/sector/us-hk-finance 4 张新表 + 19 个新端点），未触及已登记 P0/P1 资金/写锁 bug。这些仍是最高优先级。

### 新发现条目（按 CLAUDE.md 优先级 + 严重度排序）

---

### [MAJOR] `schema.py:271-535` + `docs/architecture.md:276-292` — 核心表清单未同步 11 张新表

**问题**: 第 5 轮新增 11 张表（`etfs` / `etf_nav` / `etf_financials` / `etf_fund_holdings` / `sectors` / `sector_constituents` / `us_financials` / `hk_financials` / `us_hk_ipo_calendar` / `us_hk_exdiv_calendar` / `chip_distribution` / `margintrade` / `blocktrade` / `lhb`），`docs/architecture.md` "核心表清单" 段（13 张）**未追加**。新表存在 `docs/architecture.md` 无入口、新人 onboarding 看不到这些实体。

**影响**: 文档与代码 drift；后续 agent 审查/AI 报告生成会基于过时清单。

**修复**: `docs/architecture.md` "核心表" 段补全至 26 张表（每张 1-2 行说明实体用途 + 关联关系）；同步更新 `docs/prd.md` 涉及 ETF/板块/财务数据的章节。

---

### [MAJOR] `collection_service.py:2510, 2558, 1503-1520, 1458-1477` — `raw_data.symbol` 占位符多类污染索引（合并 4 处）

**问题**: 多处 `raw_data.symbol` 写为非真实标的占位符：
- `collect_sector_*` 写 `symbol="sector"`（2 处）
- `collect_ipo` / `collect_exdiv` 写 `symbol="calendar"`（2 处）
- `collect_etf_*` 写 `symbol="etf"` 或 `market`（多处）
- `raw_data.symbol = "news"` 已有（已登记 MINOR）

`raw_data` 的 `(symbol, data_type)` 索引被这些占位符污染，**审计过滤"特定标的"时误命中"市场级"记录**。

**影响**: 违反 `raw_data` 的设计意图（按标的为粒度）；`idx_raw_data_symbol_type` 索引被低基数占位稀释。

**修复**:
1. `raw_data.symbol` 改为可空 NULL（已登记 MINOR 建议已涵盖）。
2. 新增 `raw_data.scope` 字段（`per_symbol` / `per_market` / `global`），前端按 scope 展示。
3. 同步修改 schema 文档说明 scope 语义。

---

### [MAJOR] `backend/services/collection_service.py:1940-2613` — 18 个 `collect_*` 公开方法"持锁 + 摘要 + commit" boilerplate 重复 ~700 行

**问题**: 18 个 `collect_*` 方法（含第 5 轮新增 14 个 + 旧 4 个）每个都重复：
```python
async with _WRITE_LOCK:
    log = run_logs_insert(task_name=...)
    try:
        ... 业务
    except Exception as e:
        run_logs_update(log.id, status="failure", error=str(e))
```
+ 7 个 key 的摘要 dict（"affected" / "fetched" / "skipped" / "errors"）硬编码。添加第 19 类数据需要 copy-paste ~50 行。

**影响**: 可维护性 + 已登记 MAJOR#11"4-way 重复 fetch/insert"的放大版（4 → 18）；新功能开发成本高。

**修复**: 抽 `_run_collect_with_logging(task_name, symbols, collect_fn, **summary_keys)` wrapper；同时解决 CRITICAL "13 个 collect_* 不写 run_logs" 路径。

---

### [MAJOR] `services/collection_service.py:1880-1900` — 14 个查询方法 `from_/to` 缺 ISO 格式校验（与已登记 MINOR 漏洞放大 4 倍）

**问题**: 第 5 轮新增 14 个查询方法（`get_etf_nav(symbol, from, to)` / `get_sector_performance(sector_code, from, to)` / `get_ipo_calendar(from, to)` / `get_exdiv_calendar(from, to)` / `get_chip_distribution(symbol, from, to)` 等）**全部未做日期格式校验**，原样拼入 SQL 参数化查询。坏数据（`"2026/01/01"` / `"yesterday"`）静默按字符串字典序比较（与 CRITICAL#2 同根因），返回空结果不报错。

**影响**: 已登记 MINOR #8 在第 5 轮从 1 个端点放大到 14 个端点。

**修复**:
1. 抽 `_parse_iso_date_or_422(s)` helper。
2. 所有 from/to 端点统一调用。
3. 加 Pydantic `condate()` 类型在 API 层强制。

---

### [MAJOR] `westock.py:1042-1077` — chip/margintrade/blocktrade/lhb 4 个新方法仅 A 股，无市场过滤

**问题**: 4 个新 westock 采集方法在 `__init__` 阶段无条件执行，**调用时不判断 `asset.market`**。港股/美股标的触发了不存在的 CLI 子命令 → westock 报"未知子命令"错误并被 broad `except Exception` 吞掉，但**每个非 A 股标的多一次 3-5s 失败调用**。

**影响**: 100 标的混合市场，全局失败可达 50-100 次 × 3-5s = 5-8 分钟的纯浪费。

**修复**: `if asset.market != "cn": skip + log + return` 早退；或 `if "us" in self.supported_markets and asset.market == "us": ...`。

---

### [MINOR] `portfolio_service.py:613-693` + `docs/api/portfolio.md:253` — realized-pnl 翻页 doc 与响应结构不统一

**问题**: 端点 `GET /positions/realized-pnl` 实际接受 `page`/`page_size` 并返回 `{"items": [...], "total": N, "page": N, "page_size": N}` 结构（无 `page_info` 包裹），但文档描述 "TODO 后续版本补充分页"，与代码不同步。

**影响**: 文档/代码 drift；用户按文档实现会缺失分页能力。

**修复**: 文档删除 "TODO" 段，补全分页示例；考虑统一为 `{items, total, page_info: {page, page_size, total_pages}}` 包裹格式（与已登记 UI 缓存语义一致）。

---

### [MINOR] `evidence_builder.py:43` — `_derive_finance_yoy` 用 `abs(prev_val)` 分母掩盖符号翻转

**问题**: YoY 计算 `(curr - prev) / abs(prev)`，当 `prev` 为负数时（如去年亏损）分母 `abs(prev)` 为正数，分子 `curr - prev` 可能是 `正值 - 负值` 得到正常结果，但当 `curr` 与 `prev` **同时为负但符号翻转**时（`prev=-100, curr=50`）返回 `-1.5` 看似合规实际语义错误（YoY 不该用 -1.5 表示"从亏 100 到赚 50"）。

**影响**: 财报 YoY 字段在亏损/扭亏场景下不可信。

**修复**: `if prev < 0: return None` 或单独写"扭亏"标记字段。

---

### [MINOR] `ui/pages/asset_detail.py:241-243` — 9-tab 详情页缺少新增 4 域数据对应 tab

**问题**: 第 5 轮新增 14 张表的数据（ETF / sector / us-hk finance / chip / lhb / ipo calendar / exdiv calendar）有 4 类没有对应 UI tab：
- 分红/送股（exdiv_calendar）— 没有 tab
- IPO 日历 — 没有 tab
- 龙虎榜（lhb）— 没有 tab
- 融资融券（margintrade）— 没有 tab

用户在详情页看不到这些数据，只能通过 API 取。

**影响**: 核心数据"采集了但不可见"，违背 evidence-driven 设计意图。

**修复**: 在 `ui/pages/asset_detail.py` 追加 4 个 tab（每个一个 `_render_*_tab(asset_id)` 函数 + `@st.cache_data` 包装）。

---

### [MINOR] `westock.py:1115-1147` — `blocktrade` / `lhb` 落库时 `turnover_price` / `buy_department` / `sell_department` 硬编码 None

**问题**: 4 个新采集方法的归一化层把 westock 返回的 `成交价格` / `买方营业部` / `卖方营业部` 等核心信息**未映射到列**（仅写 trade_date / symbol / volume / amount），落库时这些列写 None。**审计回查时核心信息缺失**。

**影响**: 大宗交易 + 龙虎榜数据的"最有价值信息"未入库，违背 raw_data + normalized 双写原则。

**修复**: schema 加列（`blocktrade` 加 `turnover_price` / `premium_rate`，`lhb` 加 `buy_department` / `sell_department`）；归一化层补映射。

---

### [MINOR] `jobs.py:195-213` — cleanup 任务仅清理 `raw_data`，13 张新表无清理路径

**问题**: 已登记 CRITICAL#3 "cleanup 写锁"修复后，cleanup 任务**只 `DELETE FROM raw_data WHERE collected_at < now() - 30 days`**。第 5 轮新增 13 张表（`etf_nav` / `chip_distribution` / `margintrade` / `blocktrade` / `lhb` / `ipo_calendar` 等）**无清理路径**，5-10 年后单表可膨胀到 GB 级（chip_distribution 单标的 60 天 × 100 标的 = 6000 行/年）。

**影响**: 长期使用下数据库增长失控；`raw_data` 30 天清理是补丁但治标不治本。

**修复**: cleanup 任务扩为注册表驱动：`for table, retention_days in CLEANUP_RULES.items(): DELETE FROM {table} WHERE collected_at < now() - retention_days`。

---

### [MINOR] `backend/services/collection_service.py:1066-1074` — `us_financials.raw_json` insert 路径不传

**问题**: 多数 `_insert_*` 方法把 `provider.raw_packets` 写到 `raw_data.raw_json`，但 `us_financials` / `hk_financials` 的 `_insert_*` **漏传** `raw_json` 字段（推测 SQL `INSERT INTO us_financials ...` 列表中没有 `raw_json` 列）。审计时 `raw_data` 表有财务原始 JSON，但 `us_financials` 表无法回溯到原始数据。

**影响**: 双写原则破坏；与已登记 MINOR#9 "evidence_builder raw_packets 合并"放大版同源。

**修复**: 补 `raw_json` 列到 `us_financials` / `hk_financials` 的 INSERT 列表；写一个通用 `_insert_with_raw()` helper。

---

### [MINOR] `docs/api/data.md:1-405` — 19 个新端点完全无文档

**问题**: 第 5 轮新增 19 个端点（ETF/sector/us-hk-finance/chip/margintrade/blocktrade/lhb/ipo/exdiv）**完全没有写入 `docs/api/data.md`**。已登记 MAJOR 段"neodata.md 字段名错"、"assets.md 字段名错"、本轮"portfolio.md 翻页过时" 都属同模式——文档严重 drift。

**影响**: 用户/AI agent 无法发现这些端点；与"API 规范 🟢"自评不符。

**修复**: 1 个 PR 把 `docs/api/data.md` 重写，按"端点 → 参数 → 响应 → 错误码"模板覆盖全部 19 端点；CI 加"路由列表 vs 文档列表"一致性检查。

---

### [NIT] `scheduler/jobs.py:198-209` — `_run_cleanup` 函数体内 import 风格

**问题**: 与 `NIT#7 "tencent_news.py 中文用 \u 转义"` 同模式——`from backend.storage.database import init_db_sync` 等写在函数体内而非模块顶部。可读性 + 启动期 import 顺序依赖。

**修复**: 提到模块顶部。

---

### [NIT] `collection_service.py:9, 33, 95, 1458...` — 23 处函数内 import

**问题**: 第 5 轮新增代码中 `from backend.storage.X import Y` / `from backend.services.Z import W` 散落在 23 个方法体内，违反 PEP8 风格且让"模块依赖图"无法静态分析。

**修复**: 全部提到模块顶部；按 stdlib / third-party / local 顺序。

---

### [NIT] `westock.py:62-75` — `_detect_error` 正则贪婪匹配（已登记 MAJOR 同源，但影响扩大至 9 个新方法）

**问题**: 已登记 MAJOR"westock _detect_error 错误信息不可读"——`return m.group(0).strip()` 回显触发短语。**第 5 轮新增的 chip/margintrade/blocktrade/lhb/ipo/exdiv/etf/sector/us-finance/hk-finance 10 个新 westock 方法都受此 bug 影响**，`run_logs.error_message` 全是"查询行情失败 : "。

**影响扩散**: 原 MAJOR 影响 1 个方法，**现在影响 11 个方法**。建议作为"已登记 MAJOR 的扩散面"在原条目追加注释"已扩散至 11 个方法"，**不另开新条**。

---

### [NIT] `westock.py:1011` — `_normalize_exdiv_row` market 推断启发式

**问题**: 通过 `symbol` 长度（5 = HK、6 = CN、字母 = US）推断市场，违反 CLAUDE.md "market 字段在 assets 表中"。未来加新市场需改启发式。

**修复**: 改为读 `assets.market` 表 join。

---

### [NIT] `ui/pages/ai_reports.py:110` + 14 个新端点 + `backend/main.py:74-76` lifespan 资源清理（已登记 MINOR 同源，扩散附录）

**问题**: 已登记 MINOR"lifespan 不关 provider clients" — 第 5 轮新增 4 个 Provider 类（westock_etf / westock_sector / neodata_us_finance / neodata_hk_finance）实例在 lifespan shutdown 时同样不被 close，httpx "Unclosed client" 警告数量从 6 增加到 10。**建议作为已登记 MINOR 的扩散面附录，不另开新条**。

---

## 第 5 轮 Top-5 优先修复

按 CLAUDE.md 优先级（Correctness > 采集可靠性 > 性能 > AI > UI/集成）综合排序：

1. **portfolio `create_transaction` 加 `_WRITE_LOCK`**（CRITICAL，资金写路径串行化闭环）
2. **portfolio 日期 ISO 校验 + 14 个查询端点同改**（CRITICAL，1 次性修复 15 个端点）
3. **7 个新 POST 端点加 `verify_api_key`**（CRITICAL，写端点鉴权闭环）
4. **13 个新 `collect_*` 写 `run_logs`**（CRITICAL，违反 CLAUDE.md 硬约束 + 与 18 个 boilerplate wrapper 一起重构）
5. **evidence_builder + ai_analyzer 5 个新维度评分规则**（MAJOR，evidence-driven AI 核心价值落地）

## 第 5 轮审查方法论说明

- 4-Agent 并行审查 + 中央汇总去重（本次任务）
- 4 份原始报告共 54 条候选新发现；去重 + 同源合并后 28 条入库（压缩比 52%）
- 合并类型：
  - **同根因**（10 处合并）：`run_logs` 缺失 × 2、`raw_data` 占位符 × 4、`architecture.md` 文档 × 1、us/hk finance 路由 × 3
  - **已登记问题扩散**（2 处合并）：`westock._detect_error` 11 方法扩散、`lifespan` 4 Provider 扩散
  - **同函数不同面**（2 处保留）：18 个 `collect_*` boilerplate 性能面 vs run_logs 缺失面
- 与已登记 48 条比对：0 条重复（新增表/端点/Provider 都是第 5 轮新引入的）
- 跨轮一致性：所有 CRITICAL 都涉及资金/数据正确性 + 违反 CLAUDE.md 硬约束
