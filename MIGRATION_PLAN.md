# MarketLens UI Migration: Streamlit → React + Vite + TypeScript

## Context

MarketLens 当前使用 Streamlit 构建 UI（7 个页面，~2300 行 Python 代码），存在以下痛点：
- Streamlit rerun 机制导致页面状态丢失、交互卡顿
- 复杂表格/表单/图表的可控性差
- 无法实现局部刷新、复杂导航、持久化布局
- 前后端耦合在 Python 进程中

迁移到 React + Vite + TypeScript 后，FastAPI 后端不变，UI 成为独立前端工程，通过 `/api/v1/` 接口通信。迁移分 5 个阶段，期间两个前端可并行运行。

---

## 技术选型

| 类别 | 选择 | 理由 |
|------|------|------|
| 框架 | React 19 + TypeScript 5 | 生态最大、长期可维护 |
| 构建 | Vite 6 | HMR 快、原生 TS、proxy 支持 |
| UI 组件库 | **Ant Design 5** | 中文 i18n 一等公民、金融表格/表单/Tag 开箱即用、密集布局适合数据面板 |
| 图表 | **ECharts** (echarts-for-react) | 原生 K 线/蜡烛图、红涨绿跌切换、dataZoom 适合金融时序 |
| 样式 | **Tailwind CSS** | 负责页面级布局、间距、响应式与轻量工具类；Ant Design 负责复杂组件 |
| 动画 | **framer-motion** | 负责页面切换、卡片展开、列表进出场、关键指标数字过渡 |
| API Client | openapi-typescript-codegen | 从 FastAPI `/openapi.json` 自动生成 TS 类型 + Axios client |
| 服务端状态 | **TanStack Query v5** | 直接替代 `@st.cache_data(ttl=N)` 和 `_cached_get(key, ttl, fn)`，内置 staleTime/invalidation |
| 客户端状态 | Zustand | 极轻量（1KB），仅存 API key、选中资产、侧边栏状态 |
| 路由 | React Router v7 | 7 个页面 → 7 条路由 |
| 表单 | Ant Design Form | 内建验证、嵌套字段、动态表单项 |
| 测试 | Vitest + React Testing Library + Playwright | 单元/集成/E2E |
| Lint | ESLint 9 + Prettier | TypeScript/React 规则 |
| 包管理 | **npm** | Node 自带、零配置、与 CI 集成简单 |

---

## `frontend/` 目录结构

```
frontend/
  index.html
  package.json
  package-lock.json
  tsconfig.json
  vite.config.ts          # proxy /api → localhost:8000
  tailwind.config.ts      # Tailwind 主题 token 与内容扫描
  postcss.config.js       # Tailwind/PostCSS 管线
  src/
    main.tsx              # QueryClientProvider + BrowserRouter
    App.tsx               # Router + AppLayout
    api/
      generated/          # openapi-typescript-codegen 产出
      client.ts           # Axios 实例（baseURL、拦截器、X-API-Key）
      types.ts            # 手动定义的响应类型（后端无 response_model 的补丁）
    auth/
      apiKeyStore.ts      # Zustand + localStorage 持久化 API key
    components/
      layout/
        AppLayout.tsx     # Ant Design Layout + Sider
        Sidebar.tsx       # 7 项导航
        HealthIndicator.tsx
      shared/
        PnlDisplay.tsx    # 盈亏格式化 + 颜色 + 箭头
        NumberFormat.tsx  # 万/亿 后缀
        ConfirmDelete.tsx # Modal.confirm 复用组件
        StatusTag.tsx     # 彩色状态标签
        MotionPage.tsx    # 页面切换动画容器
        MotionCard.tsx    # 卡片/列表进出场动画
    hooks/
      useHealthCheck.ts   # GET /health 30s 轮询
    pages/
      Settings/
      NewsList/
      TaskStatus/
      AiReports/
      TrackedAssets/
      Portfolio/
        tabs/PositionsTab.tsx
        tabs/TransactionsTab.tsx
        tabs/AccountsTab.tsx
      AssetDetail/
        tabs/QuoteTab.tsx ... ChipTab.tsx  (12 个 tab 组件)
    utils/
      format.ts           # 数字/货币/百分比格式化
      constants.ts        # 市场/类型/状态中文映射
    styles/
      theme.ts            # Ant Design 主题定制
      global.css
```

---

## 前后端集成方式

**开发期**：Vite dev server (5173) proxy 到 FastAPI (8000)，无需 CORS 配置。

**生产期**：FastAPI 挂载 `frontend/dist/` 静态文件（`html=True` 实现 SPA fallback），保持单进程架构：
```python
# backend/main.py 末尾
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="spa")
```

**API Key 认证**：前端首次启动弹窗输入 API key（默认 `marketlens-local`），存 localStorage，Axios 拦截器自动加 `X-API-Key` header；401 时跳转设置页重新输入。

---

## 阶段计划

### Phase 0：工程脚手架（2-3h）

创建 `frontend/` 目录，Vite + React + TS 开发服务器可运行。

**新建文件**：
- `frontend/package.json` — react, antd, @tanstack/react-query, zustand, axios, react-router-dom, dayjs, echarts, echarts-for-react
- `frontend/vite.config.ts` — proxy `/api` → `http://localhost:8000`
- `frontend/tsconfig.json`, `frontend/index.html`
- `frontend/src/main.tsx`, `frontend/src/App.tsx` — 占位页面
- `frontend/.eslintrc.cjs`, `frontend/.prettierrc`

**修改文件**：
- `.gitignore` — 添加 `frontend/node_modules/`, `frontend/dist/`

---

### Phase 1：基础设施（6-8h）

API client 生成、布局壳、认证、TanStack Query 配置、共享组件。

**1.1 API Client 生成**
```bash
cd frontend && npm run codegen
# 读取 http://localhost:8000/openapi.json → src/api/generated/
```
后端无 `response_model`，响应类型为 `any`。手动在 `src/api/types.ts` 补充接口定义，后续可给后端加 `response_model` 再重新生成。

**1.2 认证**
- `auth/apiKeyStore.ts` — Zustand + localStorage
- `api/client.ts` — Axios 拦截器：请求加 `X-API-Key`，401 清 key + 通知

**1.3 布局壳 + 路由**
- `AppLayout.tsx` — Ant Design Layout + 可折叠 Sider
- `Sidebar.tsx` — 7 项导航（追踪标的、标的详情、AI 报告、投资组合、新闻列表、任务状态、系统配置）
- `HealthIndicator.tsx` — 绿/红点 + 连接状态
- 路由：`/tracked-assets`, `/asset-detail`, `/ai-reports`, `/portfolio`, `/news`, `/task-status`, `/settings`

**1.4 共享组件**
- `PnlDisplay.tsx` — 盈亏颜色 + ▲/▼ 箭头
- `ConfirmDelete.tsx` — Modal.confirm 复用
- `NumberFormat.tsx`, `StatusTag.tsx`

**1.5 TanStack Query 配置**
```tsx
defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } }
```
- `@st.cache_data(ttl=N)` → `staleTime: N * 1000`
- `_invalidate_cache(prefix)` → `queryClient.invalidateQueries({ queryKey: [prefix] })`

---

### Phase 2：首个页面迁移 — Settings（2-3h）

选 Settings 作为首个迁移页面：最简单（纯只读、2 个 API 调用、无表单），验证全链路。

**新建文件**：
- `pages/Settings/index.tsx` — 数据源状态 Table + 调度任务频率 + 系统信息

**验证点**：API client 生成、TanStack Query 请求、Ant Design Table 渲染、HealthIndicator。

---

### Phase 3：其余页面迁移（按复杂度递增）

#### 3a：News List（2-3h）
- 单只读端点 + 3 个筛选器
- `staleTime: 60_000` 对应 `@st.cache_data(ttl=60)`

#### 3b：Task Status（3-4h）
- 引入写操作（trigger task）→ `useMutation` + `invalidateQueries`
- 验证 `X-API-Key` 认证流程

#### 3c：AI Reports（3-4h）
- 生成报告（长时 POST）+ 报告卡片展开详情
- `useMutation` + 30s 超时

#### 3d：Tracked Assets（5-6h）
- 完整 CRUD：创建/更新/删除/搜索
- Ant Design Table + 分页 + Modal Form + ConfirmDelete
- 搜索外部标的 + 添加

#### 3e：Portfolio（8-10h）
- 3 个 Tab：持仓总览、交易记录、账户管理
- 交易/账户的 CRUD Modal Form
- 盈亏显示复用 `PnlDisplay`

#### 3f：Asset Detail（12-15h）— 最复杂
- 12 个条件 Tab，每个 Tab 独立 API 调用
- 实时数据 Tab（intraday/shareholder/reserve/dividend）：`useMutation` 触发 POST + `Spin` 加载
- ETF Tab 条件渲染（仅 ETF 资产）
- ECharts 图表：NAV 折线图、筹码集中度趋势图
- K 线当前只显示指标（MA5/20/60），后续增强为蜡烛图

---

### Phase 4：清理（4-5h）

| 操作 | 文件 |
|------|------|
| 删除 Streamlit | `ui/` 目录整删 |
| 删除依赖 | `pyproject.toml` 移除 `streamlit` |
| 更新启动器 | `scripts/launcher.py`：Vite 子进程替代 Streamlit；生产模式挂载静态文件 |
| 挂载静态文件 | `backend/main.py` 末尾 `app.mount("/", StaticFiles(...))` |
| 更新 CORS | `config.yaml` 收紧为 `localhost:5173` + `localhost:8000` |
| 更新 CI | `.github/workflows/ci.yml` 增加 frontend job（npm install/lint/type-check/build/test） |
| 更新文档 | `CLAUDE.md` Commands/Architecture/Module boundaries 段落 |
| 更新 .gitignore | 添加 `frontend/node_modules/`, `frontend/dist/` |

---

## 工时估算

| 阶段 | 工时 |
|------|------|
| Phase 0 脚手架 | 2-3h |
| Phase 1 基础设施 | 6-8h |
| Phase 2 Settings | 2-3h |
| Phase 3a News | 2-3h |
| Phase 3b Task Status | 3-4h |
| Phase 3c AI Reports | 3-4h |
| Phase 3d Tracked Assets | 5-6h |
| Phase 3e Portfolio | 8-10h |
| Phase 3f Asset Detail | 12-15h |
| Phase 4 清理 | 4-5h |
| **合计** | **47-61h** |

---

## 关键权衡

1. **Ant Design vs MUI**：Ant Design 中文金融面板开箱即用，MUI 需更多自定义。
2. **ECharts vs Recharts**：ECharts 原生 K 线图，Recharts 不支持蜡烛图。ECharts 包更大但本地工具不在乎。
3. **openapi-typescript-codegen vs orval**：前者生成纯 Axios client，灵活；后者直接生成 React Query hooks，耦合更重。选前者更可控。
4. **FastAPI 挂静态文件 vs 独立静态服务器**：本地单用户工具，单进程更简单。
5. **暂不给后端加 `response_model`**：74 端点加 response_model 是大工程，先手动补前端类型，后续再改。

---

## 共存策略

迁移期间（Phase 1-3），两个前端同时可用：
- Streamlit：`uv run streamlit run ui/app.py`（8501 端口）— 未迁移页面
- React：`cd frontend && npm run dev`（5173 端口，proxy 到 8000）— 已迁移页面
- FastAPI：不变，两个前端共享同一后端

启动器（launcher.py）在 Phase 4 才切换，迁移期间开发者手动启动 Vite。

---

## 验证方式

每个阶段完成后：
1. `npm run lint && npm run type-check && npm run build` — 前端静态检查
2. `npm test` — Vitest 单元/集成测试
3. 浏览器手动测试已迁移页面 — 确认数据加载、表单提交、缓存刷新
4. `uv run pytest tests/ -v` — 后端测试不受影响
5. Phase 4 完成后：`start.bat` 一键启动 → 浏览器自动打开 → 全部页面可用
