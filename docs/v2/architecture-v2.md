# MarketLens v2 架构文档

> 版本: v2.0 (设计稿) | 日期: 2026-06-15 | 状态: **设计已定型 · 代码未启动**

> **与 v1 关系**: 本文档为 v2 设计稿。v1 完整代码与文档在 [`docs/v1/`](../v1/) 已归档保留,可继续使用。运行期 API URL 仍是 `/api/v1/`(不变),只是路径上多了一层产品版本前缀 `v1/`。
>
> **配套文档**:
> - [`docs/v2/agents-v2.md`](agents-v2.md) — 4 Agent + Orchestrator + Event Bus 详细规格
> - [`docs/architecture-v2.drawio`](../architecture-v2.drawio) — 架构图(draw.io 编辑器打开)
> - [`docs/v1/architecture.md`](../v1/architecture.md) — v1 架构(详细异步化/懒加载/数据流/Schema)

---

## 1. 文档定位

本文档回答 4 个问题:

1. v1 → v2 的核心转变是什么?
2. v2 的 6 层架构如何协作?
3. Electron 轻量壳层做什么、不做什么?
4. v1 数据层(Provider/Scheduler/SQLite)在 v2 中如何复用?

**不在本文档范围**(另见 [`agents-v2.md`](agents-v2.md)):
- Orchestrator 详细 API
- Task Graph DSL 完整 schema
- 4 Agent 各自的工具集与输入输出契约
- Event Bus 事件类型枚举与消息 envelope
- Agent Memory 三层数据模型
- Confidence Engine 三指标算法

**不在本文档范围**(后续批次):
- v2 工具层 Tool 详细规格
- v2 API 端点设计
- UI 重构的 Design Token 与组件规范

---

## 2. v1 → v2 演进对比

| 维度 | v1 (2026-06-05 之前) | v2 (2026-06-15 起) |
|------|---------------------|---------------------|
| **数据驱动** | 数据驱动:Scheduler 拉数据 → EvidenceBuilder 组装 → AIAnalyzer 出报告 | Agent 驱动:Planner 解析意图 → Task Graph → 多 Agent 并行执行 → 反馈 |
| **AI 定位** | AI 是"分析模块":用户触发 → AI 单次推理 → 输出报告 | AI 是"运行主体":持续监听事件循环,主动建议 + 被动响应 |
| **触发模型** | 用户触发:点击按钮 / 调度器定时 / API 调用 | 事件驱动:用户输入 + 监控事件 + 周期事件 → Event Bus → Agent |
| **工具角色** | 数据是被动源,工具被调用 | 工具是 Agent 的能力扩展,被 Agent 编排调用 |
| **UI 形态** | 单页 SPA + 7 个页面(Settings/NewsList/TaskStatus/AiReports/TrackedAssets/Portfolio/AssetDetail) | 多入口 UI + Electron 壳层:Chat(自然语言意图)+ Dashboard(多面板)+ Alert Panel(实时预警)+ Command Palette(快捷键)+ Thinking Trace(思维链可视化) |
| **监控能力** | 定时快照采集,无主动监控 | Monitoring Agent 持续扫描行情/新闻/资金流,主动触发 Alert |
| **学习能力** | 规则型引擎,固定权重 | Confidence Engine + Strategy Memory:AI 建议 → 实际结果 → 反馈调整规则/置信度 |
| **数据层** | 29 表 / 74 端点 / 8 Provider / 458 测试 | **完全保留 v1 数据层**,作为 v2 事实来源 |
| **运行时** | FastAPI (uvicorn) + Vite dev server / 单端口挂 dist/ | Electron 主进程 + FastAPI 子进程 + Vite 5173(开发) / Electron 打包 dist/(生产) |

---

## 3. 6 层架构总览

> **架构图**: 详见 [`docs/architecture-v2.drawio`](../architecture-v2.drawio)
> 用 draw.io Desktop 打开后,所有节点 + 边 + 反馈回路可交互编辑。
>
> **预览**: 详见本文档底部"附录 A:架构图节点对照表"。

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: UI / Interaction Layer (用户入口)                         │
│  💬 Chat │ ⌘ Command Palette │ 📊 Dashboard │ 🔔 Alert Panel │ …  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2: Agent Orchestration (大脑调度层)                          │
│  ┌─ Orchestrator ─┐  ┌─ Planner ─┐ ┌─ Research ─┐ ┌─ Portfolio ─┐ │
│  │  (注册·分发·   │  │  意图 →   │ │  行情·财报 │ │  持仓·风险   │ │
│  │   上下文·顺序)│  │  任务图   │ │  新闻·资金 │ │  盈亏归因    │ │
│  └────────────────┘  └───────────┘ └────────────┘ └──────────────┘ │
│  ┌─ Monitoring ─┐        📨 Event Bus (asyncio Queue)              │
│  │  行情·新闻  │        MARKET_UPDATE · NEWS_ALERT · USER_COMMAND │
│  │  异常资金流 │        PORTFOLIO_CHANGE · TASK_COMPLETED …       │
│  └─────────────┘                                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 3: Tool / Capability Layer (工具层)                         │
│  📈 Market │ 📰 News │ 💰 Portfolio │ 🧪 Backtest │ 📝 Report │ 🚨 Alert
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4: Evidence & Memory Layer (MarketLens 核心优势)             │
│  📦 EvidenceBuilder │ 🧠 Vector Memory │ 📊 Portfolio History     │
│  🎯 Strategy Memory │ 🧬 Agent Memory (3 层) │ 📐 Confidence Engine│
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 5: Data Ingestion Layer (v1 完整保留)                       │
│  🔌 8 Providers │ ⏰ Scheduler │ 💾 SQLite 29 表 + raw_data 审计   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 逐层职责

#### Layer 1 — UI / Interaction Layer

**职责**: 用户意图输入 + 结果展示 + 实时反馈

**组成**:
- **💬 Chat**: 自然语言意图输入(主入口)
- **⌘ Command Palette**: 快捷键唤起,所有功能命令面板
- **📊 Dashboard**: 多面板视图,Agent 实时输出
- **🔔 Alert Panel**: 实时预警面板
- **⚡ Action Bar**: 一键执行 / 撤销
- **🧠 Thinking Trace**: Agent 思维链可视化(Planner 任务图 / Agent 推理步骤)

**承载**: React 18 + Vite 5 + TypeScript 5 + Ant Design 5(沿用 v1 前端栈)

**关键原则**: UI 不直接调 Tool,所有动作走 Agent Orchestrator(IPC 桥接)。

#### Layer 2 — Agent Orchestration (大脑调度层)

**职责**: 把意图转化为可执行计划,协调多 Agent 并行 / 串行执行

**核心组件**:
- **Orchestrator**(`agent_manager.py`): Agent 注册中心 + 任务分发 + 上下文传递 + 执行顺序保证
- **Planner Agent**: 解析用户意图 → 输出 Task Graph(详见 [`agents-v2.md`](agents-v2.md) §3)
- **Research Agent**: 聚合行情/财报/新闻/资金流 → 结构化研究报告(只做事实,不做决策)
- **Portfolio Agent**: 持仓分析 + 风险暴露 + 盈亏归因 + 仓位优化建议(系统中最赚钱的 Agent)
- **Monitoring Agent**: 每分钟扫描行情 + 新闻突发 + 异常资金流 → 触发 Alert(从被动工具 → 主动系统的关键)
- **Event Bus**: asyncio Queue(轻量) / Redis pub-sub(进阶);事件类型 `MARKET_UPDATE` / `NEWS_ALERT` / `USER_COMMAND` / `PORTFOLIO_CHANGE` / `TASK_*`

**承载**: Python ≥ 3.13 + asyncio;FastAPI 主进程内嵌

**关键原则**:
- 所有 Agent 状态变更通过 Event Bus 广播,而不是直接互相调用
- Orchestrator 保证任务执行顺序(依赖边 / 并行组 / 优先级)
- Agent 输出必须带 `confidence / evidence_strength / contradiction_score` 三指标

#### Layer 3 — Tool / Capability Layer

**职责**: 提供原子能力,Agent 通过 Tool 调用协议访问

**组成**:
- **📈 Market Data Tools**: quote / kline / finance / fund_flow / technical / minute / dividend / shareholder / reserve
- **📰 News Tools**: fetch / search / sentiment / entity / event_extract
- **💰 Portfolio Tools**: positions / pnl / rebalance / risk / attribution
- **🧪 Backtest / Indicator Tools**: 策略回测 / 指标计算 / 评估指标
- **📝 Report Generator**: 研报生成 / AI 报告 / 结构化输出
- **🚨 Alert Dispatcher**: webhook / desktop notification / UI alert panel

**承载**: v1 的 8 个 Provider + 业务 Service(`CollectionService` / `NewsService` / `PortfolioService` 等)

**关键原则**:
- Tool 注册通过统一接口(`ToolRegistry`)
- Tool 调用记录全部入 `raw_data` 表(审计追溯)
- Tool 调用受 `_WRITE_LOCK` 保护(SQLite 写并发约束继承自 v1)

#### Layer 4 — Evidence & Memory Layer

**职责**: 为 Agent 提供"可追溯的事实依据" + "长期记忆"

**组成**:
- **📦 EvidenceBuilder**: 复用 v1 的 `EvidenceBuilder.build()` / `build_multi()`,为 AI 提供结构化证据包(含 `data_used` 溯源)
- **🧠 Vector Memory (news)**: 新闻向量化存储 + 语义检索(历史相似事件匹配)
- **📊 Portfolio History**: 交易历史 + 持仓快照 + 盈亏归因(继承 v1 `transactions` 表)
- **🎯 Strategy Memory**: 策略演化记录 + 置信度/胜率跟踪
- **🧬 Agent Memory (3 层)**:
  - **Short-term context**: 当前任务上下文(任务级 TTL)
  - **Strategy memory**: 用户偏好 + 历史决策
  - **Market memory**: 市场状态快照(每日收盘后冻结)
- **📐 Confidence Engine**: 三指标系统
  - `confidence`: AI 对输出的把握(0-1)
  - `evidence_strength`: 支撑证据的强度(0-1)
  - `contradiction_score`: 与历史结论的矛盾度(0-1,越高越警示)

**关键原则**:
- 所有 AI 输出必须含 `data_used` 字段,列出引用的数据源 + 采集时间(继承 v1 evidence-driven 约束)
- Agent Memory 三层用不同存储后端:Short-term 内存 dict / Strategy SQLite / Market 向量库
- Confidence Engine 的三指标影响 Strategy Memory 的权重演化

#### Layer 5 — Data Ingestion Layer

**职责**: 采集 + 持久化原始数据,作为所有上层的唯一事实来源

**组成**:
- **🔌 8 个 Providers**(v1 完整保留):
  - WeStockProvider(主力)
  - SinaProvider
  - SinaNewsProvider
  - TencentNewsProvider / TencentNewsHTTPProvider
  - RSSProvider
  - SearchEngineNewsProvider
  - NeoDataProvider
- **⏰ Scheduler**(v1 完整保留): quote (15min) / daily_close (16:00) / news (60min) / ai_report (20:00) / cleanup (3:30)
- **💾 SQLite 29 表**(v1 完整保留):
  - 核心: `tracked_assets` / `market_quotes` / `kline_daily` / `financial_reports` / `fund_flows` / `technical_indicators` / `news_items` / `ai_reports`
  - 投资组合: `accounts` / `transactions`
  - 扩展(第 5 轮+): `minute_klines` / `dividends` / `profit_forecasts` / `shareholders` / `shareholder_count_history`
  - ETF: `etf_basic` / `etf_holdings` / `etf_nav_history` / `etf_holders` / `etf_financial`
  - 板块 + 港美财务 + 日历 + 筹码: `sector_daily_quote` / `us_financials` / `ipo_exdiv_calendar` / `chip_distribution` / `margintrade_data` / `blocktrade_data` / `lhb_data`
  - 审计: `raw_data` / `run_logs`

**关键原则**:
- v2 Agent 通过 EvidenceBuilder / Tool 调用,而不是直接 SQL 查表
- Provider 失败隔离 + 单标的失败隔离(继承 v1)
- `raw_data` 表保留,作为所有 Tool 调用的审计追溯

---

## 4. Electron 轻量壳层 (Phase 1)

> **目标**: 把 v1 的"打开浏览器访问 localhost:5173/8000"升级为"双击桌面图标,后台持续运行,系统托盘 + 桌面通知 + 全局快捷键"。
>
> **不做什么**: Electron 不渲染 React UI(Phase 1),不替代 FastAPI,不承担业务逻辑。React 仍跑在 Vite / dist/ 里,Electron 只是"壳"。

### 4.1 主进程职责(5 条)

| 职责 | 说明 |
|------|------|
| 1. 系统托盘 | 启动后常驻系统托盘(Windows 右下角 / macOS 菜单栏),菜单含打开 Dashboard / 查看 Alert / 暂停监控 / 退出 |
| 2. 桌面通知 | 接收 Alert System 触发,通过 `new Notification()` 弹原生通知(Windows Action Center / macOS Notification Center) |
| 3. 全局快捷键 | 注册 3 个系统级快捷键,即使窗口最小化也能唤起 |
| 4. spawn FastAPI 子进程 | 启动时 spawn FastAPI 8000(开发模式同时 spawn Vite 5173),等待 `/api/v1/health` 200 后加载前端 |
| 5. 单实例锁 | `app.requestSingleInstanceLock()` 防止双开,第二实例触发时唤醒已有窗口 |

### 4.2 IPC Channel 清单

| Channel | Direction | Payload | 说明 |
|---------|-----------|---------|------|
| `agent:invoke` | renderer → main | `{ agent: "planner", input: {...} }` | 触发 Agent 执行 |
| `agent:cancel` | renderer → main | `{ task_id: string }` | 取消正在执行的任务 |
| `tray:show` | renderer → main | `{}` | 把窗口从托盘恢复并 focus |
| `tray:hide` | renderer → main | `{}` | 最小化到托盘 |
| `notify` | main → renderer(及 OS) | `{ title, body, urgency }` | 桌面通知触发 |
| `hotkey:registered` | main → renderer | `{ id, accelerator }` | 快捷键注册结果通知 |
| `window:focus` | main → renderer | `{}` | 窗口获焦事件(渲染 Thinking Trace) |
| `health` | renderer → main | `{}` → `{ fastapi: bool, vite: bool, version: string }` | 子进程健康检查 |

### 4.3 系统托盘菜单

```
MarketLens                            [version]
├─ 📊 打开 Dashboard           → 唤起 BrowserWindow + loadURL(localhost:5173 / dist/)
├─ 🔔 查看 Alert (3 条未读)    → 打开 Alert Panel Tab
├─ ⏸ 暂停 Monitoring Agent     → 通过 IPC 通知 Orchestrator 暂停
├─ ⚙ 设置                      → 打开 Settings Tab
├─ 📂 打开数据目录             → shell.openPath(dataDir)
├─ ─────────────────────────
├─ ❌ 退出                     → app.quit() (含 FastAPI 子进程优雅关闭)
```

### 4.4 桌面通知触发条件

| 触发源 | 通知内容 | 严重度 |
|--------|---------|--------|
| Monitoring Agent 检测到行情异动(单标的 1h 内 ±5%) | "📈 hk00700 1 小时跌幅 -5.2%,是否查看?" | normal |
| Monitoring Agent 检测到新闻突发(关键词命中追踪标的) | "📰 [突发] 比亚迪发布 Q1 业绩预告,超预期" | high |
| Monitoring Agent 检测到异常资金流(主力净流入 > 1亿) | "💰 sh600519 主力 1h 净流入 +1.2 亿" | normal |
| Alert System 用户配置阈值触发 | 用户自定义 | configurable |
| Portfolio Agent 检测到持仓风险(单标的回撤 > 10%) | "⚠ sh600519 持仓回撤 -10.5%,建议检查" | high |
| FastAPI 子进程异常退出 | "❌ FastAPI 后端已停止运行,点击重启" | critical |

### 4.5 全局快捷键表

| Accelerator | 功能 | 实现位置 |
|------------|------|---------|
| `Ctrl+Shift+M`(macOS: `Cmd+Shift+M`) | 打开 Dashboard | `globalShortcut.register` |
| `Ctrl+Shift+A`(macOS: `Cmd+Shift+A`) | 打开 Alert Panel | `globalShortcut.register` |
| `Ctrl+Shift+P`(macOS: `Cmd+Shift+P`) | 唤起 Command Palette | `globalShortcut.register` |

**注意**:
- 注册前先 `globalShortcut.unregisterAll()`,避免重复注册冲突
- 释放快捷键:`app.on('will-quit')` 钩子
- macOS 首次注册会请求辅助功能权限

### 4.6 子进程 spawn 流程

```
app.whenReady()
  ↓
1. requestSingleInstanceLock()             # 单实例锁
2. spawn FastAPI 子进程                   # python -m uvicorn backend.main:app --port 8000
3. (dev) spawn Vite dev server 子进程     # npm run dev (5173)
4. await waitForHealth('http://127.0.0.1:8000/api/v1/health', timeout=30s)
5. create BrowserWindow + loadURL(...)
   - dev: 'http://127.0.0.1:5173'
   - prod: 'http://127.0.0.1:8000'(MARKETLENS_PROD=1 单端口挂 dist/)
6. registerGlobalShortcuts()
7. createTrayMenu()
8. app.on('window-all-closed') → 保持托盘,不完全退出(Win/Linux)
9. app.on('before-quit') → 子进程优雅关闭(SIGTERM → SIGKILL 兜底)
```

**子进程管理**:
- FastAPI / Vite 子进程用 `child_process.spawn` + `detached: false`
- stdout / stderr 重定向到 `data/logs/electron-{timestamp}.log`
- 子进程崩溃 → 自动重启(最多 3 次,失败后通知用户)

### 4.7 Phase 1 → Phase 2+ 演进

| Phase | Electron 角色 | 工作量 |
|-------|---------------|--------|
| **Phase 1(当前)** | 轻量壳层:系统托盘 + 桌面通知 + 全局快捷键 + spawn FastAPI | 1-2 周 |
| Phase 2 | 接管 BrowserWindow 渲染:React 通过 preload + IPC 访问 Node API | 2-3 周 |
| Phase 3 | 打包成 .exe / .dmg / .AppImage 单文件分发 | 1-2 周 |
| Phase 4 | 离线更新(electron-updater)+ 自动启动 | 1 周 |

---

## 5. v1 数据层保留方案

> **核心原则**: v2 完全保留 v1 的所有数据层组件,作为 Agent 的事实来源。不重写、不迁移、不破坏 schema。

### 5.1 保留的 4 张核心表(Evidence 写入主战场)

| 表 | v2 中的角色 | 写入方 |
|----|-----------|--------|
| `tracked_assets` | Planner 解析意图时查询追踪列表 | AssetService / POST /assets |
| `market_quotes` / `kline_daily` / `fund_flows` / `technical_indicators` / `financial_reports` | EvidenceBuilder 直接查询组装 evidence | Scheduler(定时) + Tool Market(用户触发刷新) |
| `news_items` | Research Agent / Vector Memory 主数据源 | NewsService(每小时) |
| `transactions` / `accounts` | Portfolio Agent 主数据源 | 用户录入 / Portfolio Tools |
| `ai_reports` | Planner 决策参考 + 反馈回路(AI 建议 vs 实际结果对比) | ReportService |
| `raw_data` | 所有 Tool 调用的原始数据审计 | Tool 统一调用入口 |
| `run_logs` | 调度任务审计 + Tool 调用记录 | 所有 scheduler job + Tool 调用 |

### 5.2 不变项

- **SQLite 文件路径**: `data/marketlens.db`(沿用 v1)
- **WAL 模式 + foreign_keys=ON**: 沿用
- **`_WRITE_LOCK`(来源 `backend/services/_write_lock.py`)**: 沿用,所有写路径必须持有
- **写锁源单一化**: 严禁在 v2 模块中私有化 `threading.Lock()`(继承 v1 r15 教训)

### 5.3 新增(待 v2 代码启动后评估)

| 表候选 | 用途 | 是否已建 |
|--------|------|---------|
| `agent_runs` | 记录每个 Agent 调用的输入/输出/三指标 | 待 v2 Phase 1 评估 |
| `agent_memory_short_term` | 任务级 Short-term context 持久化(崩溃恢复) | 待 v2 Phase 1 评估 |
| `agent_strategy_history` | Strategy Memory 演化记录 | 待 v2 Phase 2 评估 |
| `alert_history` | Alert 触发记录 + 用户处理结果 | 待 v2 Phase 1 评估 |

> **Schema 变更规则**(继承 v1):
> - 所有 DDL 集中在 `backend/storage/schema.py::TABLE_DDLS` + `INDEX_DDLS`
> - 新表必须同步本文档 §5.1 + `docs/v1/architecture.md` §6.1
> - 索引与表结构必须同时在 `init_db()`(异步)和 `init_db_sync()`(测试 fixture)中可见

---

## 6. Orchestrator + 4 Agent + Event Bus(占位)

> **详细规格**: 见 [`docs/v2/agents-v2.md`](agents-v2.md)。
>
> 本节仅给出概要 + 文档跳转指针,避免重复。

| 组件 | 概要 | 详细 |
|------|------|------|
| **Orchestrator** | Agent 注册中心 + 任务分发 + 上下文传递 + 执行顺序保证 | [§2](agents-v2.md#2-orchestrator-规格) |
| **Planner Agent** | 解析用户意图 → 输出 Task Graph(`{tasks:[...]}` JSON),支持依赖边 / 并行组 / 优先级 | [§3](agents-v2.md#3-task-graph-dsl) [§4](agents-v2.md#4-planner-agent) |
| **Research Agent** | 聚合行情/财报/新闻/资金流 → 结构化研究报告(只做事实,不做决策) | [§5](agents-v2.md#5-research-agent) |
| **Portfolio Agent** | 持仓分析 + 风险暴露 + 盈亏归因 + 仓位优化建议 | [§5](agents-v2.md#5-portfolio-agent) |
| **Monitoring Agent** | 每分钟扫描行情 + 新闻突发 + 异常资金流 → 触发 Alert | [§5](agents-v2.md#5-monitoring-agent) |
| **Event Bus** | asyncio Queue(轻量) / Redis pub-sub(进阶),12 类事件枚举 | [§6](agents-v2.md#6-event-bus) |
| **Agent Memory** | Short-term / Strategy / Market 三层 | [§7](agents-v2.md#7-agent-memory-三层) |
| **Confidence Engine** | confidence / evidence_strength / contradiction_score 三指标 | [§8](agents-v2.md#8-confidence-engine) |
| **Tool 协议** | Tool interface + Registry + 鉴权传递 | [§9](agents-v2.md#9-tool-注册协议) |

---

## 7. 反馈回路:Confidence Engine → Planner

> **v2 核心创新**: v1 的 AI 是"输出即结束",v2 的 AI 持续学习。

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Planner Agent                                                  │
│   输出 Task Graph (含每步 confidence / evidence_strength)       │
│       │                                                          │
│       ▼                                                          │
│   Research / Portfolio / Monitoring 执行                         │
│   每个 Tool 调用都带 confidence 评分                              │
│       │                                                          │
│       ▼                                                          │
│   结果回写到 ai_reports + agent_runs 表                          │
│       │                                                          │
│       ▼  (N 天后)                                                │
│   Strategy Evaluator 比较"AI 当时建议" vs "实际市场结果"          │
│       │                                                          │
│       ├── 胜 → 权重提升 / 置信度提升                              │
│       ├── 负 → 权重下调 / 触发反例样本                            │
│       └── 平 → 标记"样本不足",扩大窗口再评                       │
│       │                                                          │
│       ▼                                                          │
│   Strategy Memory 更新                                           │
│   反馈给 Planner 下次推理(调整规则权重 / 引入新维度)              │
│       │                                                          │
│       └─────── 循环 ──────→                                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**关键约束**:
- `agent_runs` 表记录每次推理的完整输入 / 输出 / 三指标
- Strategy Evaluator 必须是离线 / 异步任务,不阻塞 Agent 主流程
- 反馈回路的"胜 / 负"判定有显式规则(不是 LLM 主观打分),详见 [`agents-v2.md`](agents-v2.md) §8

---

## 8. 部署形态

### 8.1 开发模式(3 进程)

```
┌────────────────────────────────────────────────────────────────┐
│ 开发模式启动                                                     │
│ $ uv run python scripts/launcher.py                            │
└────────────────────────────────────────────────────────────────┘
                │
                ├─→ Electron 主进程 (本进程)
                │     ├─ 系统托盘 + 全局快捷键
                │     ├─ spawn FastAPI 子进程 → uvicorn 8000
                │     ├─ spawn Vite dev server 子进程 → 5173
                │     └─ create BrowserWindow → loadURL(localhost:5173)
                │
                ├─→ FastAPI 8000 (uvicorn --reload)
                │     ├─ Agent Orchestrator
                │     ├─ Provider 8 个(WeStock / Sina / ...)
                │     ├─ Scheduler (quote / daily_close / news / ai_report)
                │     └─ 74 个 REST API
                │
                └─→ Vite 5173 (npm run dev)
                      └─ React + AntD UI(代理 /api → 8000)
```

**优势**: 改 Python 代码 → uvicorn reload,改 React → HMR,独立调试。

### 8.2 生产模式(单进程 + 打包)

```
┌────────────────────────────────────────────────────────────────┐
│ 生产模式启动                                                     │
│ $ MARKETLENS_PROD=1 uv run python scripts/launcher.py          │
└────────────────────────────────────────────────────────────────┘
                │
                └─→ Electron 主进程
                      ├─ 系统托盘 + 全局快捷键
                      ├─ spawn FastAPI 子进程 → uvicorn 8000(MARKETLENS_PROD=1)
                      │     └─ FastAPI mount frontend/dist(单端口)
                      └─ create BrowserWindow → loadURL(localhost:8000)
```

**Phase 3 打包**:
```
┌────────────────────────────────────────────────────────────────┐
│ Phase 3: electron-builder 打包                                  │
│ $ npm run build:electron                                        │
└────────────────────────────────────────────────────────────────┘
                │
                └─→ dist/MarketLens-Setup-x.y.z.exe (Windows)
                    dist/MarketLens-x.y.z.dmg (macOS)
                    dist/MarketLens-x.y.z.AppImage (Linux)
                      │
                      └─ 双击安装 → 桌面图标 → 单进程启动(内嵌 FastAPI)
```

### 8.3 部署形态对比

| 维度 | 开发模式 | 生产模式(Phase 1) | 打包模式(Phase 3) |
|------|---------|-------------------|-------------------|
| 进程数 | 3 | 2 | 1 |
| 用户启动方式 | `python scripts/launcher.py` | 同左 + 环境变量 | 双击桌面图标 |
| 前端 URL | localhost:5173(Vite) | localhost:8000(FastAPI 挂 dist/) | localhost:8000 |
| Python 调试 | uvicorn --reload | uvicorn(无 reload) | 内嵌 |
| React 调试 | HMR | 静态文件 | 静态文件 |
| 适用 | 开发 | 单机内测 | 用户分发 |

### 8.4 Phase 路线图

| Phase | 目标 | 状态 |
|-------|------|------|
| **v2 设计** | 6 层架构 + 4 Agent + Electron 壳层文档定型 | ✅ 当前 |
| v2 Phase 1 | 实现 Orchestrator + Planner + Research + 基础 Tool 协议 + Electron 壳层 | 待启动 |
| v2 Phase 2 | Portfolio Agent + Monitoring Agent + Alert System + Confidence Engine | 待 v2 Phase 1 完成 |
| v2 Phase 3 | Vector Memory + Strategy Memory + 反馈回路 + electron-builder 打包 | 待 v2 Phase 2 完成 |
| v2 Phase 4 | 多用户偏好 / 自定义策略 / 离线更新 | 远期 |

---

## 附录 A:架构图节点对照表

> 节点 ID 与 [`docs/architecture-v2.drawio`](../architecture-v2.drawio) 一一对应。用 draw.io 打开后,按 ID 查找可定位。

### Layer 1 节点

| ID | 中文 | 节点 ID(drawio) |
|----|------|------------------|
| 💬 Chat | 自然语言意图 | `ui_chat` |
| ⌘ Command Palette | 快捷键 | `ui_shortcut` |
| 📊 Dashboard | 多面板视图 | `ui_dashboard` |
| 🔔 Alert Panel | 实时预警面板 | `ui_alert` |
| ⚡ Action Bar | 一键执行 / 撤销 | `ui_action` |
| 🧠 Thinking Trace | Agent 思维链可视化 | `ui_thinking` |

### Layer 2 节点

| ID | 节点 ID(drawio) |
|----|------------------|
| 🧠 Orchestrator(agent_manager.py) | `orchestrator` |
| 🧭 Planner Agent(任务规划) | `planner` |
| 🔬 Research Agent(研究员) | `research` |
| 💼 Portfolio Agent(仓位智能体) | `portfolio` |
| 📡 Monitoring Agent(监控) | `monitoring` |
| 📨 Event Bus | `eventbus_box` |

### Layer 3 节点

| ID | 节点 ID(drawio) |
|----|------------------|
| 📈 Market Data | `tool_market` |
| 📰 News Tools | `tool_news` |
| 💰 Portfolio Tools | `tool_portfolio` |
| 🧪 Backtest / Indicator | `tool_backtest` |
| 📝 Report Generator | `tool_report` |
| 🚨 Alert Dispatcher | `tool_alert` |

### Layer 4 节点

| ID | 节点 ID(drawio) |
|----|------------------|
| 📦 EvidenceBuilder | `evidence_builder` |
| 🧠 Vector Memory | `vector_memory` |
| 📊 Portfolio History | `portfolio_history` |
| 🎯 Strategy Memory | `strategy_memory` |
| 🧬 Agent Memory(3 层) | `agent_memory` |
| 📐 Confidence Engine | `confidence_engine` |

### Layer 5 节点

| ID | 节点 ID(drawio) |
|----|------------------|
| 🔌 Providers(8 个) | `providers` |
| ⏰ Scheduler | `scheduler` |
| 💾 Raw Data Store | `raw_data` |

---

## 附录 B:本设计文档引用的其他文档

- [`docs/v2/agents-v2.md`](agents-v2.md) — Orchestrator / 4 Agent / Event Bus / Memory / Confidence / Tool 协议
- [`docs/architecture-v2.drawio`](../architecture-v2.drawio) — 架构图
- [`docs/v1/architecture.md`](../v1/architecture.md) — v1 架构(异步化/懒加载/Schema 详细)
- [`docs/v1/dev/lessons_learned.md`](../v1/dev/lessons_learned.md) — 23 条实操经验
- [`docs/v1/api.md`](../v1/api.md) — v1 API 概述(77 端点)

---

> **本文档为 v2 设计稿,代码未启动。** 任何与代码现状冲突时,以代码为准。

---

## 附录 C:数据契约示例

> 详细 schema 见 [`agents-v2.md`](agents-v2.md) §3 (Task Graph) / §5 (Agent 输出)。本附录给出 3 个最常用结构的最小示例。

### C.1 Evidence Package(EvidenceBuilder 输出)

```python
{
    "symbol": "hk00700",
    "as_of": "2026-06-15T16:00:00+08:00",
    "quote": {"price": 385.0, "change_pct": 1.2, "source": "westock", "collected_at": "..."},
    "kline": {"ma5": 382.5, "ma20": 378.0, "ma60": 370.0, "source": "westock", "collected_at": "..."},
    "fund_flow": {"net_flow_5d": 520000000, "trend": "连续 3 日净流入", "source": "westock"},
    "news": [
        {"title": "...", "sentiment": "positive", "importance": 3, "published_at": "..."}
    ],
    "data_used": [
        {"source": "westock", "type": "kline_daily", "collected_at": "2026-06-15T16:05:00+08:00"},
        {"source": "westock", "type": "fund_flow", "collected_at": "2026-06-15T16:05:00+08:00"},
        {"source": "sina_rss", "type": "news", "collected_at": "2026-06-15T17:00:00+08:00"}
    ]
}
```

### C.2 Task Graph(Planner 输出)

```python
{
    "plan_id": "uuid",
    "user_intent": "看看今天新能源板块能不能买",
    "tasks": [
        {"id": "t1", "agent": "research", "action": "get_sector_constituents", "params": {"sector": "新能源"}, "priority": 1},
        {"id": "t2", "agent": "research", "action": "get_fund_flow", "params": {"days": 3}, "depends_on": ["t1"]},
        {"id": "t3", "agent": "research", "action": "analyze_news_sentiment", "params": {"days": 7}, "depends_on": ["t1"]},
        {"id": "t4", "agent": "research", "action": "compute_technical", "params": {}, "depends_on": ["t1"]},
        {"id": "t5", "agent": "portfolio", "action": "score_buy_signal", "params": {}, "depends_on": ["t2", "t3", "t4"]},
        {"id": "t6", "agent": "research", "action": "generate_risk_warning", "params": {}, "depends_on": ["t5"]}
    ],
    "confidence": 0.78,
    "evidence_strength": 0.85
}
```

### C.3 Agent Run Output(任意 Agent 返回)

```python
{
    "task_id": "t5",
    "agent": "portfolio",
    "status": "success",
    "result": {
        "buy_score": 7.2,
        "action": "watch",
        "confidence": 0.72,
        "evidence_strength": 0.80,
        "contradiction_score": 0.10,
        "reasons": ["板块近 3 日主力净流入 +12 亿", "技术面 MA5 上穿 MA20"],
        "risks": ["当前估值高于历史 80 分位"],
        "data_used": [...]
    },
    "duration_ms": 2340,
    "completed_at": "2026-06-15T16:35:21+08:00"
}
```
