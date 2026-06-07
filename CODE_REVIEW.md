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

## 数据完整性 + 采集可靠性

### [CRITICAL] `news_service.py:57-151` — 新闻采集写端点绕过 `_WRITE_LOCK`

**问题**: 整个 INSERT 块（news_items + raw_data + run_logs）`with get_db() as conn` 没有 `_WRITE_LOCK`。CLAUDE.md 硬约束 "writes MUST hold `_WRITE_LOCK`"。60min 调度周期内，scheduler tick 与 API 写请求重叠时可触发 `OperationalError: database is locked`。

**修复**: 在第二个 `with get_db() as conn` 块外层加 `with _WRITE_LOCK:`。

### [CRITICAL] `scheduler/jobs.py:171-182` — `_run_cleanup` DELETE 同样绕过 `_WRITE_LOCK`

**问题**: 03:30 定时清理 `raw_data` 时，若与 `quote`/`daily_close` scheduler tick 重叠，5s busy_timeout 后可能 OperationalError。

**修复**: 同样加 `_WRITE_LOCK` 包裹。

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

### [NIT] `scheduler/jobs.py:198-209` — `_run_cleanup` 函数体内 import 风格

**问题**: 与 `NIT#7 "tencent_news.py 中文用 \u 转义"` 同模式——`from backend.storage.database import init_db_sync` 等写在函数体内而非模块顶部。可读性 + 启动期 import 顺序依赖。

**修复**: 提到模块顶部。

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

## 第 6 轮修复（2026-06-07）

> 5-Agent 并行（α split / β news run_logs / γ UI cache session_state / δ UI AI reasons 重复 / ε _run_ai_report 写锁审计）
> 1 CRITICAL 补登 + 3 条已删（split avg_cost / report_service _get_active_symbols / cache 全局清）

### [CRITICAL] `report_service.py:48-81` — `generate_reports` 写 ai_reports 缺 `_WRITE_LOCK`（**第 5 轮审查漏审**）

**问题**: `ReportService.generate_reports` 内部通过 aiosqlite 写 `ai_reports` + 通过 sync `get_db()` 写 `run_logs`，两条写路径均未持有 `_WRITE_LOCK`，违反 CLAUDE.md 硬约束。

**影响**: scheduler 60min `ai_report` 触发时，与其他写路径重叠可触发 `OperationalError: database is locked`，AI 报告可能丢失；手动 POST `/api/v1/reports/run` 同样风险。

**修复**: `report_service.py:48-81` 整段包 `with _WRITE_LOCK:`；与 `collect_quotes` 风格一致（service 层加锁，scheduler 不加）。2 个新测试（service 层 + scheduler 入口）。

