# MarketLens Issues

> 审查/issue tracker：发现新问题 → 登记 → 修复 → 删除。
> 决策历史归档在 `docs/dev/issues_YYYY-MM-DD.md`（按日期归档）。

## 当前规模

- **29 张表**（SQLite，DDL 全在 `backend/storage/schema.py::TABLE_DDLS`）
- **74 端点**（68 在 `backend/api/*.py` + 2 在 `backend/main.py` + 4 `data_sources` 子路径）
- **8 个 Provider**（`backend/collectors/*.py`：NeoData / RSS / SearchEngineNews / Sina / SinaNews / TencentNews / WeStock）
- **488 测试**（`pytest asyncio_mode = "auto"`；第 12 轮新增 19 个）

## 已知问题登记

> 新发现的 bug 在此处登记。**格式**：`### [严重度] \`文件:行号\` — 标题`
> 修复后从本节删除，归档到 `docs/dev/issues_<修复日期>.md`

<!-- 第 13 轮 React 迁移审查 -->

### [CRITICAL] `frontend/src/pages/AssetDetail/index.tsx:134-138,163-167` — 刷新 mutation 不 invalidate query，UI 显示旧数据

IntradayTab 和 ShareholderTab 的 `useMutation` 调用 `POST /data/intraday/` 或 `POST /data/shareholder/` 后，显示 `message.success("数据已更新")`，但 `useQuery` 缓存未被 invalidate，用户看到的是旧数据。

**修复**：`onSuccess` 回调中添加 `queryClient.invalidateQueries({ queryKey: ["intraday", symbol] })` / `queryClient.invalidateQueries({ queryKey: ["shareholder", symbol] })`。

### [CRITICAL] `frontend/src/api/client.ts:22-25` — 401 拦截器无条件清空 API key 且不引导用户

所有 401 响应（包括 `/health` 等不需要 key 的端点）都会触发 `useApiKeyStore.getState().clear()`，导致用户已经设置的 key 被意外清空。此外清空 key 后用户不会自动跳转到设置页面。

**修复**：
1. 401 拦截器仅对含 `X-API-Key` header 的请求清空 key（跳过 health 等公开端点）
2. 清空 key 后用 React Router 导航到 `/settings`

### [MAJOR] `frontend/src/pages/AssetDetail/index.tsx:139-143,168-172` — useQuery 调用 POST 方法做读操作

`IntradayTab` 和 `ShareholderTab` 的 `useQuery` 使用 `apiClient.post()` 获取数据。POST 每次触发都会写 `raw_data`（后端采集再返回），意味着：
- 页面每次 mount/mount 或 staleTime 过期时会触发新一次采集
- 与 mutation 重复调用同一端点

后端已有 GET 端点（`data.py:218` GET `/data/shareholder/{symbol}` 等），应改用 GET 查询历史数据，仅 mutation 用 POST 触发刷新。

**修复**：`useQuery` 改用 GET 端点获取缓存数据；mutation 用 POST 触发新采集 + invalidate。

### [MAJOR] `frontend/src/components/layout/Sidebar.tsx:31` — selectedKeys 无法匹配子路由

`selectedKeys={[location.pathname]}` 在访问 `/asset-detail` 时高亮菜单，但 `/asset-detail` 实际没有列表页（用户通过下拉选择），当 URL 变成 `/asset-detail?id=1` 或类似路径时菜单不高亮。

**修复**：使用最长前缀匹配：
```ts
const selected = ITEMS.map(i => i.key)
  .sort((a, b) => b.length - a.length)
  .find(k => location.pathname === k || location.pathname.startsWith(k + "/"));
```

### [MAJOR] `frontend/src/components/shared/ConfirmDelete.tsx:17` — onConfirm 异步错误被静默吞掉

`Modal.confirm({ onOk: onConfirm })` 中 `onConfirm` 是 `() => void` 类型。如果调用方传入 `async` 函数（如 `() => remove.mutate(id)`），Promise reject 会被 antd 吞掉，模态框关闭，用户看不到错误。

**修复**：
```ts
onOk: async () => {
  try { await onConfirm(); }
  catch (e) { message.error(extractErrorMessage(e)); throw e; }
},
```

### [MAJOR] `frontend/src/utils/format.ts:10-13` — formatPercent 与 formatNumber 不一致，不处理 Infinity

- `formatNumber` 使用 `toLocaleString("zh-CN", ...)`（有千分位），`formatPercent` 使用 `toFixed()`（无千分位），同一 UI 里 `1,234.56` vs `1234.56%`
- 两个函数都不守卫 `Infinity` / `-Infinity`（除零可能出现），导致渲染 `Infinity%`
- `value > 0 ? "+" : ""` 对 `0.0001.toFixed(2) = "0.00%"` 产生 `+0.00%`

**修复**：
```ts
export function formatPercent(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: "exceptZero",
  }) + "%";
}
```

### [MAJOR] `frontend/src/components/layout/HealthIndicator.tsx:17` — "degraded" 状态被当作连接失败

`ok = !isError && data?.status === "ok"` 导致 `status === "degraded"` 时显示红点 + "API 连接失败"。对用户来说这是误报——degraded 意味部分功能可用。

**修复**：增加三态处理：
```ts
const status = isError ? "error" : data?.status === "ok" ? "ok" : "degraded";
// ok → 绿点 "已连接", degraded → 黄点 "部分降级", error → 红点 "连接失败"
```

### [MAJOR] `frontend/src/pages/Settings/index.tsx:117` + `TaskStatus/index.tsx:114` — 所有非 success 状态统一标红

`status === "success" ? "green" : "red"` 把 "running"/"pending" 也标红，语义错误。

**修复**：定义状态颜色映射表：
```ts
const STATUS_COLORS: Record<string, string> = {
  success: "green", failed: "red", running: "blue", pending: "default",
};
```

### [MAJOR] `frontend/src/api/types.ts:77,93-95,124` — 联合类型末尾 `| string` 使类型检查失效

`"buy" | "sell" | string` 等价于 `string`，TypeScript 无法做穷尽检查。要么删除 `| string` 使用严格联合类型，要么直接用 `string`（因后端未用 response_model 约束）。

**修复**：删除 `| string`，改用严格枚举：
```ts
action: "buy" | "sell" | "watch" | "avoid";
risk_level: "low" | "medium" | "high";
sentiment: "positive" | "negative" | "neutral" | null;
```
如果后端实际可能返回未知值，在 API client 层做 fallback 处理。

### [MAJOR] `backend/storage/schema.py:705-741` — raw_data 迁移无事务保护，FK 断面风险

`_migrate_raw_data_symbol_nullable_sync` 执行 `PRAGMA foreign_keys=OFF` → 表重建 → `PRAGMA foreign_keys=ON` 无事务包裹。如果 INSERT 步骤中途失败（磁盘满等），数据库处于不一致状态：旧表已删、新表不完整、FK 仍关闭。

**修复**：
1. 用 `try/finally` 保证 FK 恢复
2. 用 `BEGIN IMMEDIATE; ... COMMIT;` 包裹迁移
3. 替换脆弱的 `split("symbol")` NOT NULL 检测为 `PRAGMA table_info(raw_data)`

### [MAJOR] `backend/main.py:86-100` — Provider 关闭直接访问 Service 私有成员

`lifespan` 中 `_get_collection_service()._get_structured_providers()` 和 `_get_news_service()._providers` 访问 Service 私有方法/属性，违反封装。如果 Service 重构重命名，`main.py` 会静默崩溃。

**修复**：在 Service 类上添加公开方法 `close_all_providers()` 或 `get_providers()`。

### [MAJOR] `scripts/launcher.py:83-110` — Vite 子进程输出完全丢弃

`stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` 意味着 Vite 启动失败时（端口冲突、config 错误等）没有任何日志可查。`_wait_for_url` 超时后用户只看到 "UI 在 30s 内未就绪"。

**修复**：将 stdout/stderr 重定向到日志文件或通过 `logger` 输出：
```python
log_file = open(log_dir / "vite-dev.log", "a")
kwargs = {"stdout": log_file, "stderr": subprocess.STDOUT}
```

### [MAJOR] `scripts/launcher.py:215-220` — watch_task 清理通过名称查找 task 不可靠

`_watch_stop` task 通过 `asyncio.all_tasks()` + `get_name() == "_watch_stop"` 查找，可能误匹配其他模块的同名 task。task 变量已在局部作用域，可直接引用。

**修复**：移除名称查找，直接引用局部变量 `task`：
```python
if task is not None and not task.done():
    task.cancel()
    try: await task
    except (asyncio.CancelledError, Exception): pass
```

### [MINOR] `frontend/src/App.tsx:16-24` — 无 ErrorBoundary 包裹 lazy route

`React.lazy` 加载失败（网络断开、chunk 丢失）会导致整个 App 白屏。`Suspense` 只处理 pending 状态，不处理 rejection。

**修复**：添加 ErrorBoundary 组件包裹每个 `withSuspense` 的返回值。

### [MINOR] `frontend/src/components/shared/MotionCard.tsx` + `MotionPage.tsx` — 未尊重 prefers-reduced-motion

`framer-motion` 动画会在用户设置了"减少动画"（Windows "减少动画效果" / macOS "减少动态效果"）时仍然播放。应使用 `useReducedMotion()` 判断。

**修复**：`const shouldReduce = useReducedMotion();` 然后条件渲染 `initial`/`animate`。

### [MINOR] `frontend/src/pages/Portfolio/index.tsx:84` — Position 行 rowKey 用 account_id + symbol 可能不唯一

如果同一账户同一标的多笔持仓，复合 key `${account_id}-${symbol}` 重复。

**修复**：API 应返回唯一 ID，或前端用 index 作 key（如果数据不增删）。

### [MINOR] `frontend/src/api/client.ts:2,24` — 使用 antd 静态 `message.error` 而非 context API

antd 的 `message.error()` 静态调用在 v5 下会生成控制台警告（"Static function can not consume context like dynamic theme"），且无法跟随 ConfigProvider 的 locale/theme。

**修复**：在 AppLayout 中使用 `App.useApp().message` 并通过 React context 传入 interceptor，或创建全局 message holder。

### [MINOR] `frontend/src/auth/apiKeyStore.ts:14` — 默认 API key "marketlens-local" 持久化到 localStorage

首次启动即写入 localStorage，用户无法区分"从未设置"和"主动设置为默认值"。如果后端部署时改了 key，用户前端会一直发旧 key。

**修复**：默认值设为空字符串 `""`，在 Settings 页看到空 key 时引导用户配置。

### [MINOR] `frontend/src/components/layout/AppLayout.tsx:39` — 硬编码后端 URL

`http://localhost:8000` 直接写死在组件中，在不同部署环境下无法覆盖。

**修复**：使用 `import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"`。

### [MINOR] `frontend/src/utils/format.ts:2-7` — formatNumber 不处理 Infinity

`Number.isNaN` 只检测 NaN，`Infinity` 会渲染为 `Infinity`。

**修复**：将守卫条件改为 `if (value === null || value === undefined || !Number.isFinite(value))`。

### [MINOR] `frontend/src/hooks/useHealthCheck.ts` — 缺少 `refetchIntervalInBackground: false`

30s 轮询在 Tab 隐藏时仍然运行，浪费电池和请求。

**修复**：添加 `refetchIntervalInBackground: false` 到 useQuery 配置。

### [NIT] `scripts/launcher.py:34-40` — `_resolve_project_root` 两个分支返回相同值

`if getattr(sys, "frozen", False)` 和 `else` 都返回 `Path(__file__).resolve().parent.parent`，条件可删除。

### [NIT] `scripts/launcher.py:224` — `"browser_task" in locals()` 判断

改为在 `_run` 函数开头声明 `browser_task: asyncio.Task | None = None`，用 `browser_task is not None` 代替 `locals()` 检查。

### [NIT] `frontend/src/components/shared/PnlDisplay.tsx` — 缺少 `aria-label`

屏幕阅读器会读取 "绿色标签 ▲ 1.23%" 而非"盈亏 正 1.23%"。添加 `aria-label={`盈亏 ${formatPercent(value)}`}`。

### [NIT] `frontend/src/components/shared/StatusTag.tsx:11` — null 时显示 "-" 与真实数据不可区分

改为 `<Typography.Text type="secondary">无</Typography.Text>` 明确表示"无数据"。

### [NIT] `frontend/src/components/layout/AppLayout.tsx:21` — Emoji 📊 未标记为装饰性

屏幕阅读器会朗读"图表"。添加 `aria-hidden="true"` 并用 `<span>` 包裹，或替换为 antd Icon。

## 历史归档

- `docs/dev/issues_2026-06-08.md` — 第 4-11 轮审查 70+ 条 + 9 轮修复决策历史
- `docs/dev/issues_2026-06-08_r12.md` — 第 12 轮审查 11 条 + 修复（CRITICAL 1 + MAJOR 5 + MINOR 3 + NIT 2）