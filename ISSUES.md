# MarketLens Issues

> 审查/issue tracker：发现新问题 → 登记 → 修复 → 删除。
> 决策历史归档在 `docs/dev/issues_YYYY-MM-DD.md`（按日期归档）。

## 当前规模

- **29 张表**（SQLite，DDL 全在 `backend/storage/schema.py::TABLE_DDLS`）
- **74 端点**（68 在 `backend/api/*.py` + 2 在 `backend/main.py` + 4 `data_sources` 子路径）
- **8 个 Provider**（`backend/collectors/*.py`：NeoData / RSS / SearchEngineNews / Sina / SinaNews / TencentNews / WeStock）
- **495 测试**（`pytest asyncio_mode = "auto"`；第 13 轮新增 2 个迁移测试 + 1 个 lifespan 测试）

## 已知问题登记

> 新发现的 bug 在此处登记。**格式**：`### [严重度] \`文件:行号\` — 标题`
> 修复后从本节删除，归档到 `docs/dev/issues_<修复日期>.md`

### 第 15 轮前端审查（2026-06-11，从误用的 CODE_REVIEW.md 迁回）

审查范围：`frontend/` React 层 + 前端关联后端 API 端点

#### CRITICAL

##### C2. `NewsItem.importance` 类型错误：前端 `number | null` vs 后端 `TEXT`（"normal"/"high"/"low"）

- **文件**: `frontend/src/api/types.ts:78`, `backend/storage/schema.py:132`, `backend/collectors/tencent_news_http.py:111-115`
- **问题**: 前端定义 `importance?: number | null`，但后端所有 Provider 均写入 string（"normal"/"high"/"low"），schema DDL 为 `TEXT`。前端若对该字段做数值比较或格式化，会静默失败。
- **影响**: 所有新闻列表中 `importance` 字段实际值为字符串，前端无法正确按重要性排序/过滤。
- **修复**: 将 `importance` 类型改为 `string | null`，并在 UI 层增加 `IMPORTANCE_LABELS` 映射。

##### C3. `/positions/realized-pnl` 返回扁平分页，前端按 `PageResult<RealizedPnlItem>` 解析会丢失 `page_info`

- **文件**: `backend/services/portfolio_service.py:797-802`, `frontend/src/api/types.ts:27-30`, `frontend/src/components/layout/KpiBar.tsx:22`, `frontend/src/pages/Portfolio/index.tsx:55`
- **问题**: 后端 `get_realized_pnl` 返回 `{items, total, page, page_size}`（扁平格式），而非标准 `PageResult<T> = {items, page_info: {page, page_size, total, total_pages}}`。KpiBar 和 Portfolio 页都按 `PageResult` 解析，`data.page_info` 为 `undefined`，分页元数据丢失。
- **影响**: `realized.data?.page_info` 为 `undefined`，`total` 等字段无法正确读取。KpiBar 使用 `items` 求和所以数值结果恰好正确，但 Portfolio 页若增加分页控件会完全失败。
- **修复**: 后端改为标准 `PageResult` 格式（`{items, page_info: {...}}`），或在后端包装一层。保持全项目分页响应一致。

#### MAJOR

##### M1. `RealizedPnlItem` 缺少 `avg_cost` 字段

- **文件**: `frontend/src/api/types.ts:146-151`, `backend/services/portfolio_service.py:792`
- **问题**: 后端返回 `avg_cost` 字段，前端类型未声明。Portfolio 页表格列已展示 `avg_cost`（通过 `Position`），但 `RealizedPnlItem` 缺少该字段意味着未来已实现盈亏详情页无法显示均价。
- **修复**: 在 `RealizedPnlItem` 中添加 `avg_cost: number`。

##### M2. `Transaction` 缺少 `updated_at` / `deleted_at` 字段

- **文件**: `frontend/src/api/types.ts:120-132`
- **问题**: 后端 account 端点返回 `updated_at`，soft-delete 时返回 `deleted_at`。但前端 `Transaction` 类型只有 `created_at`，缺少这两个字段。若 UI 需显示"最近修改时间"或区分已删除记录，字段缺失将导致运行时 undefined。
- **修复**: 添加 `updated_at?: string` 和 `deleted_at?: string | null`。

##### M3. `AssetDetail.kline_summary` 缺少 `latest_close` 字段

- **文件**: `frontend/src/api/types.ts:166`
- **问题**: 后端的 `kline_summary` 包括 `latest_close` 字段，但前端类型仅定义了 `{ma5, ma20, ma60, trend}`。如果 UI 未来需要在 K 线面板展示最新收盘价，该字段不可用。
- **修复**: 扩展 `kline_summary` 类型加入 `latest_close?: number`。

##### M4. `/data-sources/status` 响应结构与 `DataSourceItem` 不匹配

- **文件**: `frontend/src/api/types.ts:32-45`, `backend/api/data_sources.py:164-183`
- **问题**: `DataSourceItem` 定义了扁平结构（`category, name, provider, type, enabled, optional, timeout`），但 `/status` 端点返回的对象包含额外字段：`has_token`, `token_source`, `token_expires_at`, `token_verified`, `command`, `executable`, `command_resolved`, `endpoint`。这些字段在 `DataSourceItem` 中未声明。
- **影响**: Settings 页如需显示数据源健康状态（token 是否过期、命令是否可解析），当前类型无法表达。
- **修复**: 新增 `DataSourceStatusItem` 类型，或在 `DataSourceItem` 中添加 optional 字段。

##### M5. CommandPalette 搜索资产传 `search` 参数但后端 `list_assets` 不支持

- **文件**: `frontend/src/components/shared/CommandPalette.tsx:104`, `backend/api/assets.py:58-76`, `backend/services/asset_service.py:171-220`
- **问题**: CommandPalette 调用 `apiClient.get("/assets", { params: { search, page: 1, page_size: 10 } })`，但 `list_assets` 端点只接受 `enabled`/`market`/`asset_type`/`tag`/`page`/`page_size`。`search` 参数被后端静默忽略。
- **影响**: 用户在命令面板输入关键词搜索资产时，结果不包含过滤，始终返回全部标的的前 10 条。
- **修复**: 方案 A：给 `list_assets` 后端增加 `search` 查询参数（symbol/name 模糊匹配）。方案 B：CommandPalette 改用 `/assets/search` 端点。

##### M6. `AssetDetail` 继承 `latest_price`/`latest_change_pct` 但详情端点可能不返回

- **文件**: `frontend/src/api/types.ts:153`, `backend/api/assets.py:79-87`
- **问题**: `AssetDetail extends TrackedAsset`，继承了 `latest_price` 和 `latest_change_pct`。但 `get_asset_by_id` 端点返回的详情数据是否包含这两个字段取决于服务层 JOIN 逻辑——如果标的没有最近行情记录，这两个字段将不存在或为 null。代码中使用 `??: null` 可避免崩溃，但类型定义暗示一定存在。
- **修复**: 确认后端详情端点确实不返回这两个字段后从 `AssetDetail` 显式排除，或确认返回后标注可空。

##### M7. 写操作缺少前端 `Create*Request` / `Update*Request` 类型

- **文件**: `frontend/src/api/types.ts`
- **问题**: 后端定义了 `CreateAccountRequest`、`UpdateAccountRequest`、`CreateTransactionRequest`、`UpdateTransactionRequest`、`AssetCreateRequest`、`AssetUpdateRequest` 等 Pydantic 模型，但前端 `types.ts` 没有任何对应的请求类型。写操作 payload 使用裸 `Partial<TrackedAsset>` 推导，无法捕获字段缺失或类型错误。
- **影响**: 写操作的请求体不受 TypeScript 保护，字段名拼写错误或遗漏只在运行时暴露。
- **修复**: 新增 `CreateAssetRequest`、`CreateAccountRequest`、`CreateTransactionRequest` 等请求类型，用于 mutation payload。

#### MINOR

##### m1. `NewsItem.related_symbols` 类型过宽：后端始终返回 `string[]`，前端标记为 `string[] | null`

- **文件**: `frontend/src/api/types.ts:79`
- **问题**: 后端 `news_service.py` 在正常路径下构造 `related_symbols` 为 `json.loads()` 结果（默认 `[]`），前端标记 `| null` 无害但语义不准。
- **修复**: 改为 `related_symbols?: string[]`（去掉 `| null`），或确认后端确实可能返回 null 后保留。

##### m2. `Transaction.currency` 标记 optional 但后端始终返回非 null

- **文件**: `frontend/src/api/types.ts:128`
- **问题**: 后端 `PortfolioService` 在返回交易时始终填充 `currency`（来源 account 或默认 `"CNY"`），前端标注 `currency?: string | null` 虽无害但语义松散。
- **修复**: 改为 `currency: string`。

##### m3. `AIReport.name` 在列表端点中不填充

- **文件**: `frontend/src/api/types.ts:92`
- **问题**: `AIReport.name` 字段定义为 `string | null`，但后端 AI 报告列表端点不返回 `name` 字段（只有详情端点返回含 `name` 的完整报告）。前端 AI 报告页若展示 `report.name`，会显示 `null`。
- **修复**: 确认前端只使用 `symbol` + `action` 作为标题；或在后端列表端点补全 `name`。

##### m4. `CollectionTimeline` 缺少分页滚动加载

- **文件**: `frontend/src/components/shared/CollectionTimeline.tsx:21-30`
- **问题**: 固定 `page_size=50`，当采集日志超过 50 条时无法查看更早的记录。组件没有"加载更多"或无限滚动。
- **修复**: 可选优化——添加 "加载更多" 按钮或 IntersectionObserver 无限滚动。

#### NIT

##### n1. 已实现盈亏分页 — Portfolio 页未实现翻页 UI

- **文件**: `frontend/src/pages/Portfolio/index.tsx:55-58`
- **问题**: `realized` 查询缺省 `page_size=50`（后端默认），但未传 `page`/`page_size` 参数，也未在 UI 渲染分页控件。当已实现盈亏记录超过 50 条时，用户只能看到前 50 条。
- **修复**: 如需求支持大量记录，添加 Ant Design `Pagination` 组件；否则当前规模可忽略。

##### n2. `CommandPalette` 搜索与 `TrackedAssets` 搜索使用不同 API 路径

- **文件**: `frontend/src/components/shared/CommandPalette.tsx:104` vs `frontend/src/pages/TrackedAssets/index.tsx:102`
- **问题**: 一个使用 `/assets?search=`（被后端忽略），另一个使用 `/assets/search?keyword=`。两个搜索入口当前都不可用。
- **修复**: 统一使用 `/assets/search?keyword=` 端点。

##### n3. `KpiBar` 和 `Portfolio` 页对 `realized-pnl` 查询的 TypeScript 类型不一致

- **文件**: `frontend/src/components/layout/KpiBar.tsx:22` vs `frontend/src/pages/Portfolio/index.tsx:55`
- **问题**: KpiBar 声明 `useQuery<{ items: RealizedPnlItem[] }>`（无 `total`），Portfolio 声明 `useQuery<{ items: RealizedPnlItem[]; total: number }>`（不含 `page/page_size`）。两者对同一端点的类型描述不同。
- **修复**: 统一使用 `PageResult<RealizedPnlItem>`（修 C3 后）。

##### n4. 主题切换未持久化（需确认）

- **文件**: `frontend/src/components/layout/ThemeToggle.tsx`
- **问题**: 需确认 ThemeToggle 是否将用户选择持久化到 localStorage。若未实现，页面刷新后主题选择丢失。
- **修复**: 检查 ThemeToggle 实现，若未持久化则添加。

---

### 第 16 轮：UI/UX + 无用文件 + 前后端交互（2026-06-12）

审查方向（用户指定 3 个维度）：(1) 前端交互是否好看；(2) 是否存在无用的文件；(3) 前后端交互是否存在问题。

#### CRITICAL

##### C4. AI 报告生成请求 30s 超时不足，长任务必然失败

- **文件**: `frontend/src/api/client.ts:49`, `frontend/src/pages/AiReports/index.tsx:50-54`
- **问题**: axios 实例全局 `timeout: 30_000`。`POST /reports/generate` 跨多个标的同步执行规则引擎 + 证据组装，10 个标的串行约 30-90s，必定超时。前端报"Network Error"，但后端实际仍在执行（产生孤儿任务）。
- **影响**: 用户点"生成报告"看到错误提示，但后端报告已生成；导致重复触发，DeepSeek 配额浪费 + 数据库重复 INSERT 风险（虽有 UNIQUE INDEX 兜底，但 raw_data 仍会重复写）。
- **修复**: 方案 A——`/reports/generate` 这一个请求传 `timeout: 180_000`。方案 B——后端改异步：`POST /reports/generate` 立即返 202 + task_id，前端轮询 `/tasks/status` 看进度。**单用户本地工具优先方案 A**（简单可靠）。

#### MAJOR

##### M8. Settings 页"未设置 API Key" Alert 误导用户

- **文件**: `frontend/src/pages/Settings/index.tsx:73-80`, `frontend/src/auth/apiKeyStore.ts:24-26`
- **问题**: Settings 仅在 `!apiKey.trim()` 时显示 Alert"需要补充 API Key 才能修改投资组合"，但 `getApiKey()` 在 store 为空时**返回默认 `marketlens-local`**，实际请求时一定带 X-API-Key 头且后端接受该默认值（CLAUDE.md 已明确豁免）。Alert 文案让用户以为不写就不能用，事实相反。**且 Settings 页根本没有 API Key 输入框**，即使用户想写也无入口。
- **影响**: 用户被误导，尝试找输入框未果，可能放弃使用核心功能。
- **修复**:
  1. 若设计就是"默认本地 key 足够" → 删除 Alert 或改文案为"已使用默认本地 API Key，如需自定义请编辑 localStorage `marketlens_api_key`"；
  2. 若需要支持自定义 → 在 Alert 旁加 `<Input.Password>` + 保存按钮调 `useApiKeyStore.setState({ key })`。

##### M9. Settings 页未显示 NeoData token 健康状态，与 CLAUDE.md 设计矛盾

- **文件**: `frontend/src/pages/Settings/index.tsx:31-67`, `backend/api/data_sources.py:163-183`
- **问题**: CLAUDE.md 明确写 "若需 UI 提示用户'该去 workbuddy 刷新 token'，使用 `GET /api/v1/data-sources/status` 的 `neodata` 字段"。但 Settings 页只调 `/data-sources/config`（拿不到 `has_token` / `token_verified` / `token_expires_at`），完全缺少 NeoData token 状态展示。当 token 过期时，用户在 UI 看不到任何线索，只能从 run_logs 错误信息倒推。
- **修复**: Settings 增加对 `/data-sources/status` 的 useQuery，对 NeoData 行加状态列（已配置/缺失/已验证/已过期）+ 提示"请在 workbuddy 中刷新 token"。

##### M10. TaskStatus 触发任务后无主动轮询，60s 长任务用户体感"卡死"

- **文件**: `frontend/src/pages/TaskStatus/index.tsx:65-77`
- **问题**: 用户点"立即触发"后只看到 `message.success("已触发")`，`invalidateQueries({queryKey: ["tasks"]})` 会立刻 refetch 一次但此时任务刚启动，`last_status` 仍是上次结果。`staleTime: 15_000` + 默认不轮询 → 用户必须 15s 后自己点页面刷新或切换 tab 才能看到新状态。AI 报告 60-90s，期间用户会反复点触发按钮重复提交。
- **修复**: trigger mutation `onSuccess` 后启动短周期轮询：`refetchInterval: 3_000` 持续 5 次，或直到 `last_status !== "running"`。可用 TanStack `useQuery` 的 `enabled` + 局部 state 实现。

##### M11. Portfolio 持仓 + 已实现盈亏列显示 `account_id` 数字而非账户名

- **文件**: `frontend/src/pages/Portfolio/index.tsx:68,99`
- **问题**: 表格"账户"列直接 `dataIndex: "account_id"`，渲染为 `1`、`2` 这类数字。用户必须切到 AccountsTab 自己查 id → name 映射。
- **影响**: 多账户用户 P&L 归属难以辨认，违反"信息友好"原则。
- **修复**: PositionsTab 内 join 已查到的 `accounts` query 数据（注意 PositionsTab 没查 accounts，需新增 useQuery + 跨 query memo 拼接），渲染 `account.name`，title 显示 id 便于排查。

##### M12. PnlDisplay/StatusTag 用 Tailwind `text-gray-400` 与 CSS 变量主题双轨

- **文件**: `frontend/src/components/shared/PnlDisplay.tsx:23`, `frontend/src/components/shared/StatusTag.tsx:13`
- **问题**: 项目主题用 CSS 变量 `--color-text-tertiary`（浅色 `#999`、深色 `#737373`），但 PnlDisplay/StatusTag 的"空值"占位用 Tailwind 预设 `text-gray-400`（固定 `#9CA3AF`）。深色模式下出现 3 套灰度：tertiary token `#737373`、Tailwind `gray-400` `#9CA3AF`、secondary token `#A3A3A3`，肉眼可辨。
- **影响**: 主题切换时灰度跳变，"未设置"标签与同行其他次要文字色差异常。
- **修复**: 改用 `style={{ color: "var(--color-text-tertiary)" }}` 或在 tailwind.config.js 把 `gray.400` 重映射到 token。

##### M13. AppLayout 内 Sider `theme="light"` 在深色模式下导致 Menu 内部 token 不切换

- **文件**: `frontend/src/components/layout/AppLayout.tsx:24`
- **问题**: Sider 自己背景被 `style.background: var(--color-bg-container)` 覆盖（深色下变 `#1F1F1F` 没问题），但 `theme="light"` prop 会强制 AntD Menu 内部使用浅色 token——hover 色、选中色、文字色仍按浅色算。深色模式下选中项呈白底蓝字、hover 灰带白底，与 Sider 深色背景对比错乱。
- **修复**: 删除 `theme="light"` prop（让 ConfigProvider 全局主题接管），或读 `data-theme` 动态传 `theme={isDark ? "dark" : "light"}`。

##### M14. AiReports / NewsList / Portfolio / TrackedAssets 错误展示不统一，无重试

- **文件**: `frontend/src/pages/AiReports/index.tsx:83-91`, `frontend/src/pages/NewsList/index.tsx`, `frontend/src/pages/Portfolio/index.tsx:83`, `frontend/src/pages/Settings/index.tsx:85-89,115-118`
- **问题**: 7 个页面对 API 失败统一渲染 `<Typography.Text type="danger">加载失败：{msg}</Typography.Text>`，但**无重试按钮、无错误类型区分（4xx/5xx/timeout）**，与 `RouteErrorBoundary` 使用 antd `<Result>` 的视觉风格也不一致。429（理论上不会出现）和 504 看起来都一样。
- **修复**: 抽 `<QueryErrorState onRetry={refetch} error={err} />` 共用组件，包 `Result` + 重试按钮。

##### M15. AssetDetail 容器高度写死 `h-[calc(100vh-200px)]`

- **文件**: `frontend/src/pages/AssetDetail/index.tsx`（如 agent 报告的行号 120）
- **问题**: `200px` 是 Header(64) + Content padding(24×2) + KpiBar(~60) + Title 区的粗估。浏览器 zoom ≠ 100% 或 KpiBar 折行时底部内容会露白或被裁。Tailwind 任意值 calc 也不响应主题/字号变化。
- **修复**: 改用父级 `flex flex-col flex-1 min-h-0` + 子容器 `flex-1 min-h-0 overflow-auto`，避免硬编码数值。

#### MINOR

##### m5. 项目根 `UTF8` 是测试残留（11 字节 `-Encoding\r\n`）

- **文件**: `UTF8`
- **问题**: 文件内容是 `-Encoding\r\n`，是某个 PowerShell `Set-Content -Encoding ...` 命令把参数当文件名残留。无任何代码/CI/文档引用。
- **修复**: `git rm UTF8`。

##### m6. 旧架构图 drawio 文件未删除

- **文件**: `MarketLens金融研究助理系统架构.drawio`
- **问题**: 旧版架构图，包含"CLI/移动端 / 向量索引 / 规则与风控 / 即时问答"等**未实现**模块。当前唯一活跃架构图是 `react-vite-fastapi-architecture.drawio`（2026-06-10 生成）。文件路径含中文，CI/grep 不易处理。
- **修复**: `git rm` 旧文件，仅保留 `react-vite-fastapi-architecture.drawio`。

##### m7. `data/seed_test_data.py` 和 `data/start_backend.bat` 是已废弃残留

- **文件**: `data/seed_test_data.py`, `data/start_backend.bat`
- **问题**:
  - `seed_test_data.py`：182 行测试数据注入脚本，最后一次引用是 `8f3ca92 测试功能`，无任何后续调用。
  - `start_backend.bat`：4 行，硬编码绝对路径 `D:\Project\MarketLens`（worktree 中跑会指错位置）。根 `start.bat` 已覆盖功能。
- **修复**: `git rm data/seed_test_data.py data/start_backend.bat`。同时检查 `.gitignore` 是否需增加 `data/*.bat`。

##### m8. `scripts/verify_sentiment.py` 自称临时脚本但未删

- **文件**: `scripts/verify_sentiment.py`
- **问题**: 文件首行注释明确写"临时验证脚本"，160 行，未在 CI/launcher/scheduler 注册。情感分析功能已 7bf67e2/0d073e3 落地稳定。
- **修复**: `git rm scripts/verify_sentiment.py`，或迁到 `tests/scripts/` 作为可重复运行的人工验证。

##### m9. `PLAN.md` 全部复选框未勾选，状态与实际仓库进展不符

- **文件**: `PLAN.md`
- **问题**: 9KB 的 P0-P2 UI 升级计划，所有 `- [ ]` 项目仍未勾，但仓库 commit 已经在做 sentiment 等其他方向，不再按 PLAN 推进。
- **修复**: 迁到 `docs/dev/plan_r15_2026-06-11.md` 归档，或直接删除（git 仍保留历史）。

##### m10. CLAUDE.md 第 421-426 行仍引用已删除的 `ui/app.py` / `ui/pages/portfolio.py`

- **文件**: `CLAUDE.md:421-426`
- **问题**: 第 12 轮 Streamlit 迁移后 `ui/` 整个目录已删除。CLAUDE.md "Issue tracker 迁移"段提及"`ui/app.py` 1 处注释 / `ui/pages/portfolio.py` 1 处 docstring"作为引用迁移成果，对新会话接手时是误导（会让 Agent 去搜不存在的文件）。
- **修复**: 删除这 2 行历史脚注，或注明"已随 Streamlit 移除"。

##### m11. apiClient response interceptor 仅处理 401，404/422/500 完全交给页面

- **文件**: `frontend/src/api/client.ts:60-69`
- **问题**: response interceptor 只在 401 时清 store + 提示"API Key 无效"。404（资产已删）/ 422（参数无效）/ 500（后端错）/ 网络断（`error.code === "ERR_NETWORK"`）/ 超时（`error.code === "ECONNABORTED"`）都未在拦截器统一处理，每个页面 useQuery 自己写 `isError ? <Text danger>`。
- **影响**: 错误体验碎片化，超时只显示"timeout of 30000ms exceeded"对用户不友好。
- **修复**: interceptor 增加对 `ECONNABORTED` 的提示"请求超时，请稍后重试"，对 502/503/504 提示"后端服务暂不可用"。具体页面错误（404/422）保持页面级处理即可。

##### m12. NewsList Tab `related_symbols` 蓝色 Tag 看着可点击但无 onClick

- **文件**: `frontend/src/pages/NewsList/index.tsx:137`
- **问题**: 新闻条目展示相关标的代码用 `<Tag color="blue">600519</Tag>`，蓝色 + 类似超链接外观让用户预期点击跳转到 AssetDetail，实际无 onClick 处理。
- **修复**: 加 `onClick={() => navigate(\`/asset-detail/${sym}\`)}` + `style={{cursor: "pointer"}}` + Tooltip "查看该标的详情"。

#### NIT

##### n5. 添加交易 Modal 缺 `account_id` 默认值

- **文件**: `frontend/src/pages/Portfolio/index.tsx:185`
- **问题**: `initialValues: { type: "buy", trade_date: dayjs() }` 没给 `account_id` 默认值。首次使用必须从下拉选；若用户当前只有 1 个账户，重复多次添加交易会重复选同一项。
- **修复**: `initialValues` 增加 `account_id: accounts.data?.[0]?.id`。

##### n6. CommandPalette 缺键盘提示 (`⌘K`/`Ctrl+K` 入口可见性)

- **文件**: `frontend/src/components/layout/AppLayout.tsx`（Header）
- **问题**: CommandPalette 已实现，但顶部 Header 无任何 `⌘K` badge 或 `?` 帮助按钮，新用户不知道存在快捷键。
- **修复**: Header 右侧 `<Space>` 加 `<Tag>⌘K 搜索</Tag>` 点击可触发，或 Sidebar 底部加 "按 ⌘K 搜索" 文字。

##### n7. global.css 命令面板选中态 `color: #fff` 硬编码

- **文件**: `frontend/src/styles/global.css:192`
- **问题**: `[cmdk-item][aria-selected="true"] { background: var(--color-primary); color: #fff; }` 中 `#fff` 是硬编码。当前 `--color-primary` 是深蓝 `#0F2D5C` / 深色 `#3B82F6`，白字对比度 OK，但若品牌色换浅色会破。
- **修复**: 提取 `--color-on-primary: #fff;` 语义 token，让主题层面可控。

##### n8. ConfirmDelete 未禁用 ESC

- **文件**: `frontend/src/components/shared/ConfirmDelete.tsx:12`
- **问题**: `Modal.confirm` 未传 `keyboard: false`，用户按 ESC 可直接关闭确认框等同"取消"。删除等危险操作允许键盘"误关"虽不致命但与"二次确认"语义稍有矛盾。
- **修复**: `Modal.confirm({ keyboard: false, ... })`。

##### n9. theme-color meta 硬编码颜色不跟 token 变化

- **文件**: `frontend/src/main.tsx:46`
- **问题**: `theme-color` meta 写死 `#141414` / `#FFFFFF`，主题色调整时无人会想起改这个。影响移动浏览器顶栏配色（虽然桌面不可见）。
- **修复**: 用 `document.querySelector('meta[name=theme-color]')` 在 ThemeToggle 切换时同步更新，或直接从 CSS 变量读 `--color-bg-base`。

##### n10. AssetDetail 3 栏分隔条 `w-1.5`（6px）过窄

- **文件**: `frontend/src/pages/AssetDetail/index.tsx:126,135`
- **问题**: `react-resizable-panels` Separator 宽度 6px，桌面鼠标拖拽尚可，但 hover 触发区域偏小，找不到拖手柄。
- **修复**: `w-3`（12px）+ 中间画 2px 实线作为视觉指示。

## 历史归档

- `docs/dev/issues_2026-06-08.md` — 第 4-11 轮审查 70+ 条 + 9 轮修复决策历史
- `docs/dev/issues_2026-06-08_r12.md` — 第 12 轮审查 11 条 + 修复（CRITICAL 1 + MAJOR 5 + MINOR 3 + NIT 2）
- `docs/dev/issues_2026-06-11_r13.md` — 第 13 轮 React 迁移审查 27 条全部修复（CRITICAL 2 + MAJOR 13 + MINOR 7 + NIT 4 + 补充 MAJOR 1）
- `docs/dev/issues_2026-06-11_r14.md` — 第 14 轮前端审查 6 条全部修复（MAJOR 2 + MINOR 3 + NIT 1）