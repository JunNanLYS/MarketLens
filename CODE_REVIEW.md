# 前端 UI 审查登记

审查范围：`frontend/` React 层 + 前端关联后端 API 端点
审查日期：2026-06-11

---

## CRITICAL

### C2. `NewsItem.importance` 类型错误：前端 `number | null` vs 后端 `TEXT`（"normal"/"high"/"low"）

- **文件**: `frontend/src/api/types.ts:78`, `backend/storage/schema.py:132`, `backend/collectors/tencent_news_http.py:111-115`
- **问题**: 前端定义 `importance?: number | null`，但后端所有 Provider 均写入 string（"normal"/"high"/"low"），schema DDL 为 `TEXT`。前端若对该字段做数值比较或格式化，会静默失败。
- **影响**: 所有新闻列表中 `importance` 字段实际值为字符串，前端无法正确按重要性排序/过滤。
- **修复**: 将 `importance` 类型改为 `string | null`，并在 UI 层增加 `IMPORTANCE_LABELS` 映射。

### C3. `/positions/realized-pnl` 返回扁平分页，前端按 `PageResult<RealizedPnlItem>` 解析会丢失 `page_info`

- **文件**: `backend/services/portfolio_service.py:797-802`, `frontend/src/api/types.ts:27-30`, `frontend/src/components/layout/KpiBar.tsx:22`, `frontend/src/pages/Portfolio/index.tsx:55`
- **问题**: 后端 `get_realized_pnl` 返回 `{items, total, page, page_size}`（扁平格式），而非标准 `PageResult<T> = {items, page_info: {page, page_size, total, total_pages}}`。KpiBar 和 Portfolio 页都按 `PageResult` 解析，`data.page_info` 为 `undefined`，分页元数据丢失。
- **影响**: `realized.data?.page_info` 为 `undefined`，`total` 等字段无法正确读取。KpiBar 使用 `items` 求和所以数值结果恰好正确，但 Portfolio 页若增加分页控件会完全失败。
- **修复**: 后端改为标准 `PageResult` 格式（`{items, page_info: {...}}`），或在后端包装一层。保持全项目分页响应一致。

---

## MAJOR

### M1. `RealizedPnlItem` 缺少 `avg_cost` 字段

- **文件**: `frontend/src/api/types.ts:146-151`, `backend/services/portfolio_service.py:792`
- **问题**: 后端返回 `avg_cost` 字段，前端类型未声明。Portfolio 页表格列已展示 `avg_cost`（通过 `Position`），但 `RealizedPnlItem` 缺少该字段意味着未来已实现盈亏详情页无法显示均价。
- **修复**: 在 `RealizedPnlItem` 中添加 `avg_cost: number`。

### M2. `Transaction` 缺少 `updated_at` / `deleted_at` 字段

- **文件**: `frontend/src/api/types.ts:120-132`
- **问题**: 后端 account 端点返回 `updated_at`，soft-delete 时返回 `deleted_at`。但前端 `Transaction` 类型只有 `created_at`，缺少这两个字段。若 UI 需显示"最近修改时间"或区分已删除记录，字段缺失将导致运行时 undefined。
- **修复**: 添加 `updated_at?: string` 和 `deleted_at?: string | null`。

### M3. `AssetDetail.kline_summary` 缺少 `latest_close` 字段

- **文件**: `frontend/src/api/types.ts:166`
- **问题**: 后端的 `kline_summary` 包括 `latest_close` 字段，但前端类型仅定义了 `{ma5, ma20, ma60, trend}`。如果 UI 未来需要在 K 线面板展示最新收盘价，该字段不可用。
- **修复**: 扩展 `kline_summary` 类型加入 `latest_close?: number`。

### M4. `/data-sources/status` 响应结构与 `DataSourceItem` 不匹配

- **文件**: `frontend/src/api/types.ts:32-45`, `backend/api/data_sources.py:164-183`
- **问题**: `DataSourceItem` 定义了扁平结构（`category, name, provider, type, enabled, optional, timeout`），但 `/status` 端点返回的对象包含额外字段：`has_token`, `token_source`, `token_expires_at`, `token_verified`, `command`, `executable`, `command_resolved`, `endpoint`。这些字段在 `DataSourceItem` 中未声明。
- **影响**: Settings 页如需显示数据源健康状态（token 是否过期、命令是否可解析），当前类型无法表达。
- **修复**: 新增 `DataSourceStatusItem` 类型，或在 `DataSourceItem` 中添加 optional 字段。

### M5. CommandPalette 搜索资产传 `search` 参数但后端 `list_assets` 不支持

- **文件**: `frontend/src/components/shared/CommandPalette.tsx:104`, `backend/api/assets.py:58-76`, `backend/services/asset_service.py:171-220`
- **问题**: CommandPalette 调用 `apiClient.get("/assets", { params: { search, page: 1, page_size: 10 } })`，但 `list_assets` 端点只接受 `enabled`/`market`/`asset_type`/`tag`/`page`/`page_size`。`search` 参数被后端静默忽略。
- **影响**: 用户在命令面板输入关键词搜索资产时，结果不包含过滤，始终返回全部标的的前 10 条。
- **修复**: 方案 A：给 `list_assets` 后端增加 `search` 查询参数（symbol/name 模糊匹配）。方案 B：CommandPalette 改用 `/assets/search` 端点（但需先修 C1）。

### M6. `AssetDetail` 继承 `latest_price`/`latest_change_pct` 但详情端点可能不返回

- **文件**: `frontend/src/api/types.ts:153`, `backend/api/assets.py:79-87`
- **问题**: `AssetDetail extends TrackedAsset`，继承了 `latest_price` 和 `latest_change_pct`。但 `get_asset_by_id` 端点返回的详情数据是否包含这两个字段取决于服务层 JOIN 逻辑——如果标的没有最近行情记录，这两个字段将不存在或为 null。代码中使用 `??: null` 可避免崩溃，但类型定义暗示一定存在。
- **修复**: 确认后端详情端点确实不返回这两个字段后从 `AssetDetail` 显式排除，或确认返回后标注可空。

### M7. 写操作缺少前端 `Create*Request` / `Update*Request` 类型

- **文件**: `frontend/src/api/types.ts`
- **问题**: 后端定义了 `CreateAccountRequest`、`UpdateAccountRequest`、`CreateTransactionRequest`、`UpdateTransactionRequest`、`AssetCreateRequest`、`AssetUpdateRequest` 等 Pydantic 模型，但前端 `types.ts` 没有任何对应的请求类型。写操作 payload 使用裸 `Partial<TrackedAsset>` 推导，无法捕获字段缺失或类型错误。
- **影响**: 写操作的请求体不受 TypeScript 保护，字段名拼写错误或遗漏只在运行时暴露。
- **修复**: 新增 `CreateAssetRequest`、`CreateAccountRequest`、`CreateTransactionRequest` 等请求类型，用于 mutation payload。

---

## MINOR

### m1. `NewsItem.related_symbols` 类型过宽：后端始终返回 `string[]`，前端标记为 `string[] | null`

- **文件**: `frontend/src/api/types.ts:79`
- **问题**: 后端 `news_service.py` 在正常路径下构造 `related_symbols` 为 `json.loads()` 结果（默认 `[]`），前端标记 `| null` 无害但语义不准。
- **修复**: 改为 `related_symbols?: string[]`（去掉 `| null`），或确认后端确实可能返回 null 后保留。

### m2. `Transaction.currency` 标记 optional 但后端始终返回非 null

- **文件**: `frontend/src/api/types.ts:128`
- **问题**: 后端 `PortfolioService` 在返回交易时始终填充 `currency`（来源 account 或默认 `"CNY"`），前端标注 `currency?: string | null` 虽无害但语义松散。
- **修复**: 改为 `currency: string`。

### m3. `AIReport.name` 在列表端点中不填充

- **文件**: `frontend/src/api/types.ts:92`
- **问题**: `AIReport.name` 字段定义为 `string | null`，但后端 AI 报告列表端点不返回 `name` 字段（只有详情端点返回含 `name` 的完整报告）。前端 AI 报告页若展示 `report.name`，会显示 `null`。
- **修复**: 确认前端只使用 `symbol` + `action` 作为标题；或在后端列表端点补全 `name`。

### m4. `CollectionTimeline` 缺少分页滚动加载

- **文件**: `frontend/src/components/shared/CollectionTimeline.tsx:21-30`
- **问题**: 固定 `page_size=50`，当采集日志超过 50 条时无法查看更早的记录。组件没有"加载更多"或无限滚动。
- **修复**: 可选优化——添加 "加载更多" 按钮或 IntersectionObserver 无限滚动。


---

## NIT

### n1. 已实现盈亏分页 — Portfolio 页未实现翻页 UI

- **文件**: `frontend/src/pages/Portfolio/index.tsx:55-58`
- **问题**: `realized` 查询缺省 `page_size=50`（后端默认），但未传 `page`/`page_size` 参数，也未在 UI 渲染分页控件。当已实现盈亏记录超过 50 条时，用户只能看到前 50 条。
- **修复**: 如需求支持大量记录，添加 Ant Design `Pagination` 组件；否则当前规模可忽略。

### n2. `CommandPalette` 搜索与 `TrackedAssets` 搜索使用不同 API 路径

- **文件**: `frontend/src/components/shared/CommandPalette.tsx:104` vs `frontend/src/pages/TrackedAssets/index.tsx:102`
- **问题**: 一个使用 `/assets?search=`（被后端忽略），另一个使用 `/assets/search?keyword=`（被路由遮蔽返回 422）。两个搜索入口当前都不可用。
- **修复**: 修 C1 后统一使用 `/assets/search?keyword=` 端点。

### n3. `KpiBar` 和 `Portfolio` 页对 `realized-pnl` 查询的 TypeScript 类型不一致

- **文件**: `frontend/src/components/layout/KpiBar.tsx:22` vs `frontend/src/pages/Portfolio/index.tsx:55`
- **问题**: KpiBar 声明 `useQuery<{ items: RealizedPnlItem[] }>`（无 `total`），Portfolio 声明 `useQuery<{ items: RealizedPnlItem[]; total: number }>`（不含 `page/page_size`）。两者对同一端点的类型描述不同。
- **修复**: 统一使用 `PageResult<RealizedPnlItem>`（修 C3 后）。

### n4. 主题切换未持久化（需确认）

- **文件**: `frontend/src/components/layout/ThemeToggle.tsx`
- **问题**: 需确认 ThemeToggle 是否将用户选择持久化到 localStorage。若未实现，页面刷新后主题选择丢失。
- **修复**: 检查 ThemeToggle 实现，若未持久化则添加。