# MarketLens v2 Agent 详细规格

> 版本: v2.0 (设计稿) | 日期: 2026-06-15 | 状态: **设计已定型 · 代码未启动**

> **配套文档**:
> - [`docs/v2/architecture-v2.md`](architecture-v2.md) — 6 层架构 + Electron 壳层 + 部署形态
> - [`docs/architecture-v2.drawio`](../architecture-v2.drawio) — 架构图
>
> **范围**: 本文档定义 v2 Agent 系统的详细规格——Orchestrator、4 个 Agent、Task Graph DSL、Event Bus、Agent Memory、Confidence Engine、Tool 协议。所有"v2 设计稿,代码未启动"。

---

## 1. 文档定位

本文档回答 7 个问题:

1. **Orchestrator 怎么注册和分发 Agent?**
2. **Task Graph DSL 长什么样?**
3. **4 个 Agent(Planner / Research / Portfolio / Monitoring)各自做什么?**
4. **Agent 之间怎么通信?Event Bus 上跑哪些事件?**
5. **Agent 怎么"记住"事情?三层 Memory 怎么落地?**
6. **AI 输出的可信度怎么量化?**
7. **Tool 怎么注册和调用?**

**不在本文档范围**:
- 6 层架构总览 → [`architecture-v2.md`](architecture-v2.md) §3
- Electron 壳层 / IPC → [`architecture-v2.md`](architecture-v2.md) §4
- v1 数据层保留 → [`architecture-v2.md`](architecture-v2.md) §5
- 反馈回路 → [`architecture-v2.md`](architecture-v2.md) §7

---

## 2. Orchestrator 规格

### 2.1 职责

Orchestrator(`backend/agents/orchestrator.py`)是 Agent 系统的中枢,负责:

| 职责 | 说明 |
|------|------|
| **注册** | 启动时注册所有 Agent(Planner / Research / Portfolio / Monitoring) |
| **分发** | 接收 Task Graph,按依赖顺序 + 并行组 + 优先级分发给对应 Agent |
| **上下文** | 为每个 Agent 调用准备"上下文"(Short-term Memory + 当前 Evidence + 上游 Agent 输出) |
| **执行顺序** | 维护 DAG 拓扑序,保证 `depends_on` 全部完成才执行下游 |
| **超时控制** | 每个 Agent 调用有超时(默认 30s,可在 Task Graph 中覆盖) |
| **错误隔离** | 单个 Agent 失败不影响其他 Agent 的执行 |
| **反馈给 UI** | 把每个 Agent 的 Thinking Trace 实时推送给 renderer(Electron IPC) |

### 2.2 Agent 注册表

```python
# backend/agents/orchestrator.py
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "planner": PlannerAgent,
    "research": ResearchAgent,
    "portfolio": PortfolioAgent,
    "monitoring": MonitoringAgent,
}

class BaseAgent(ABC):
    @abstractmethod
    async def execute(self, task: Task, context: AgentContext) -> AgentResult: ...
    @abstractmethod
    def get_capabilities(self) -> list[str]: ...   # 列出该 Agent 能处理的 action
```

### 2.3 任务分发算法

```python
async def dispatch(plan: TaskGraph) -> list[AgentResult]:
    """按依赖顺序 + 并行组并行执行 Task Graph。"""
    completed: dict[str, AgentResult] = {}
    pending = {t.id: t for t in plan.tasks}
    in_flight: set[asyncio.Task] = set()

    while pending or in_flight:
        # 找出所有依赖已完成的任务
        ready = [
            t for t in pending.values()
            if all(dep in completed for dep in t.depends_on)
        ]
        # 并行启动所有 ready 任务
        for task in ready:
            ctx = build_context(task, completed, plan)
            agent = AGENT_REGISTRY[task.agent]()
            in_flight.add(asyncio.create_task(agent.execute(task, ctx)))
            pending.pop(task.id)

        # 等待任意一个完成
        done, in_flight = await asyncio.wait(
            in_flight, return_when=asyncio.FIRST_COMPLETED
        )
        for t in done:
            result = t.result()
            completed[result.task_id] = result
            emit_event("task.completed", result)

    return list(completed.values())
```

### 2.4 上下文传递

```python
def build_context(task: Task, completed: dict, plan: TaskGraph) -> AgentContext:
    """为当前任务构造 Agent 上下文。"""
    return AgentContext(
        # 1. 上游 Agent 的输出
        upstream_results=[
            completed[dep] for dep in task.depends_on
            if dep in completed
        ],
        # 2. Evidence(从 EvidenceBuilder 拉,按 symbol 缓存)
        evidence=evidence_cache.get(task.params.get("symbol", "")),
        # 3. Short-term Memory
        short_term=short_term_memory.get(task.id),
        # 4. 全局 plan 上下文(用户意图 + 置信度)
        plan_context={
            "user_intent": plan.user_intent,
            "plan_confidence": plan.confidence,
            "evidence_strength": plan.evidence_strength,
        },
    )
```

### 2.5 Thinking Trace 推送

```python
async def execute(self, task: Task, context: AgentContext) -> AgentResult:
    """Agent 内部每一步推理都 emit 一个 trace 事件。"""
    emit_event("thinking.trace", {
        "task_id": task.id,
        "step": "evidence_loaded",
        "detail": f"Loaded evidence with {len(context.evidence)} fields",
    })
    emit_event("thinking.trace", {
        "task_id": task.id,
        "step": "reasoning",
        "detail": "Analyzing MA5 vs MA20 crossover...",
    })
    return AgentResult(...)
```

**Renderer 端订阅**(`window.api.on('thinking.trace', ...)`)显示在 Thinking Trace 面板。

---

## 3. Task Graph DSL

### 3.1 设计目标

| 目标 | 说明 |
|------|------|
| **显式依赖** | 每个 Task 声明 `depends_on`,避免隐式 ordering |
| **并行组** | 多个无依赖的 Task 自动并行执行 |
| **优先级** | 同 ready 队列中,priority 高的先调度(资源紧张时) |
| **可序列化** | JSON-friendly,Planner 输出直接落 DB |
| **可重放** | Task Graph + 当时 Evidence 可重放任意一次执行 |
| **可中断** | 任意 Task 可被 `agent:cancel` 终止,后续 Task 标记为 cancelled |

### 3.2 完整 Schema

```python
class TaskGraph(BaseModel):
    plan_id: str                                 # UUID
    user_intent: str                             # 原始用户输入
    created_at: datetime                         # 任务图生成时间
    tasks: list[Task]                            # 任务列表
    confidence: float                            # Planner 对整个图的置信度(0-1)
    evidence_strength: float                     # Planner 推理所依据的 Evidence 强度
    metadata: dict[str, Any] = {}                # 扩展字段(用户偏好 / 时间窗口 / 市场状态)


class Task(BaseModel):
    id: str                                      # 任务 ID,plan 内唯一
    agent: Literal["research", "portfolio", "monitoring", "planner"]
    action: str                                  # 该 Agent 能处理的 action 之一
    params: dict[str, Any] = {}                  # action 的输入参数
    depends_on: list[str] = []                   # 依赖的 Task ID 列表
    priority: int = 5                            # 1(高) - 10(低),默认 5
    timeout_s: int = 30                          # 超时(秒)
    retry_on_failure: bool = False               # 失败是否自动重试(最多 1 次)


class TaskResult(BaseModel):
    task_id: str
    agent: str
    status: Literal["success", "failure", "cancelled", "timeout"]
    result: dict[str, Any] | None = None         # 成功时的输出
    error: str | None = None                     # 失败时的错误信息
    confidence: float = 0.0                     # 该 Task 结果的置信度
    evidence_strength: float = 0.0               # 该 Task 引用证据的强度
    contradiction_score: float = 0.0             # 与历史结论的矛盾度
    duration_ms: int = 0
    started_at: datetime
    completed_at: datetime
    thinking_trace: list[dict] = []              # 推理步骤(供 UI 显示)
    data_used: list[dict] = []                   # 引用的数据源 + 采集时间(evidence-driven 约束)
```

### 3.3 Planner 输出示例

```python
{
    "plan_id": "plan-uuid-1234",
    "user_intent": "看看今天新能源板块能不能买",
    "created_at": "2026-06-15T16:30:00+08:00",
    "tasks": [
        {
            "id": "t1",
            "agent": "research",
            "action": "get_sector_constituents",
            "params": {"sector": "新能源", "limit": 20},
            "priority": 1
        },
        {
            "id": "t2",
            "agent": "research",
            "action": "get_fund_flow",
            "params": {"symbols": "<from t1>", "days": 3},
            "depends_on": ["t1"],
            "priority": 3
        },
        {
            "id": "t3",
            "agent": "research",
            "action": "analyze_news_sentiment",
            "params": {"symbols": "<from t1>", "days": 7},
            "depends_on": ["t1"],
            "priority": 3
        },
        {
            "id": "t4",
            "agent": "research",
            "action": "compute_technical",
            "params": {"symbols": "<from t1>", "indicators": ["MA", "MACD", "RSI"]},
            "depends_on": ["t1"],
            "priority": 3
        },
        {
            "id": "t5",
            "agent": "portfolio",
            "action": "score_buy_signal",
            "params": {"fund_flow": "<from t2>", "news": "<from t3>", "technical": "<from t4>"},
            "depends_on": ["t2", "t3", "t4"],
            "priority": 1
        },
        {
            "id": "t6",
            "agent": "research",
            "action": "generate_risk_warning",
            "params": {"buy_signal": "<from t5>"},
            "depends_on": ["t5"],
            "priority": 1
        }
    ],
    "confidence": 0.78,
    "evidence_strength": 0.85
}
```

**注意**: `<from t1>` 是 Planner 输出时的占位符,Orchestrator 在 dispatch 前会替换成 t1 的实际结果。

### 3.4 重规划触发条件

Planner 不是一次性的。当以下情况发生时,Orchestrator 触发 Planner 重新生成 Task Graph:

| 触发条件 | 说明 |
|---------|------|
| **关键任务失败** | 任意 `priority=1` 的 Task 失败且 `retry_on_failure=False` |
| **Evidence 突变** | 任务执行中触发了 Monitoring Agent 的 Alert(行情异动 / 新闻突发) |
| **超时** | 整个 Plan 执行超过 `plan_timeout_s`(默认 5 分钟) |
| **用户主动中断** | 用户在 UI 点"重新规划",带新输入 |
| **矛盾度过高** | 任意 Task 结果的 `contradiction_score > 0.7` |

重规划时,Planner 接收原始 `user_intent` + 当前所有 `completed` Task 结果 + 新的 Evidence。

---

## 4. Planner Agent

### 4.1 输入契约

```python
class PlannerInput(BaseModel):
    user_intent: str                             # 用户的自然语言输入
    context: AgentContext                        # 当前上下文(Short-term Memory + 当前 Strategy Memory + 当前 Market Memory)
    available_actions: dict[str, list[str]]      # 各 Agent 能处理的 action 列表(从 Orchestrator 注册表动态获取)
```

### 4.2 输出契约

`TaskGraph`(见 §3.2)

### 4.3 实现路径

| 阶段 | 实现 |
|------|------|
| **v2 Phase 1** | **规则型 Planner**: 预定义意图模板,匹配后输出固定 Task Graph。覆盖 80% 高频意图 |
| **v2 Phase 2** | **LLM Planner**: 用 Claude / GPT-4 生成 Task Graph,基于 `available_actions` 约束输出 |
| **v2 Phase 3** | **混合 Planner**: 规则匹配高频意图 + LLM 处理长尾 |

**Phase 1 规则模板示例**(伪代码):

```python
INTENT_TEMPLATES = [
    {
        "match": ["新能源", "板块"],
        "graph": [
            {"agent": "research", "action": "get_sector_constituents"},
            {"agent": "research", "action": "get_fund_flow", "depends_on": ["t1"]},
            {"agent": "research", "action": "analyze_news_sentiment", "depends_on": ["t1"]},
            {"agent": "portfolio", "action": "score_buy_signal", "depends_on": ["t2", "t3"]},
        ]
    },
    {
        "match": ["持仓", "风险"],
        "graph": [
            {"agent": "portfolio", "action": "analyze_holdings"},
            {"agent": "portfolio", "action": "compute_risk_exposure", "depends_on": ["t1"]},
            {"agent": "portfolio", "action": "suggest_rebalance", "depends_on": ["t2"]},
        ]
    },
]
```

### 4.4 失败处理

| 失败类型 | 处理 |
|---------|------|
| **意图无法匹配任何模板** | 返回 fallback Task Graph:`{"tasks": [{"agent": "research", "action": "clarify_intent"}]}`,提示用户细化输入 |
| **LLM 输出 schema 不合法** | 重试 1 次,失败后用 fallback |
| **Task Graph 含未注册 action** | 拒绝 dispatch,返回 `INVALID_PLAN` 错误给用户 |

---

## 5. Research / Portfolio / Monitoring Agent

> 三个 Agent 共享 BaseAgent 接口,但职责差异显著。下面平铺规格。

### 5.1 Research Agent(研究员)

**职责**: 聚合行情/财报/新闻/资金流 → 输出结构化研究报告。**只做事实,不做决策**。

**工具集**(`get_capabilities()` 返回):

| Action | 输入 | 输出 |
|--------|------|------|
| `get_sector_constituents` | `{sector, limit}` | `{symbols: [...], as_of: ...}` |
| `get_quote` | `{symbols}` | `{quotes: [...], source, collected_at}` |
| `get_kline` | `{symbol, days}` | `{klines: [...], source, collected_at}` |
| `get_finance` | `{symbol, limit}` | `{reports: [...], source, collected_at}` |
| `get_fund_flow` | `{symbols, days}` | `{flows: [...], summary, source}` |
| `get_technical` | `{symbol, indicators}` | `{indicators: {...}, source}` |
| `get_news` | `{symbols, days, sentiment}` | `{news: [...], source}` |
| `analyze_news_sentiment` | `{symbols, days}` | `{aggregated_sentiment, breakdown_by_symbol, source}` |
| `compute_technical` | `{symbols, indicators}` | `{results: {...}, source}` |
| `generate_research_report` | `{all_upstream_results}` | `{report: {...}, confidence, evidence_strength}` |
| `generate_risk_warning` | `{upstream_results}` | `{warnings: [...], risk_level}` |
| `clarify_intent` | `{raw_intent, candidates}` | `{question: str}` |

**输入**: 来自 Orchestrator 的 `AgentContext`(含上游 Evidence + 用户意图)

**输出**: `TaskResult`(`status="success"`, `result={...}`, `confidence`, `evidence_strength`)

**失败处理**:
- 单个 Tool 调用失败 → 标记 `status="failure"`,error_message,不影响 Plan 中其他 Task
- 多个上游结果矛盾 → `contradiction_score > 0.7`,Orchestrator 触发 Planner 重规划
- 关键 Tool(quote / kline)缺失 → 返回 `evidence_strength < 0.3`,Research Agent 主动建议"证据不足"

### 5.2 Portfolio Agent(仓位智能体) ⭐

**职责**: 持仓分析 + 风险暴露 + 盈亏归因 + 仓位优化建议。**系统中最赚钱的 Agent**。

**工具集**:

| Action | 输入 | 输出 |
|--------|------|------|
| `analyze_holdings` | `{account_id?}` | `{positions: [...], summary: {...}, source}` |
| `compute_pnl_attribution` | `{positions, days}` | `{attribution: {...}, total_pnl, source}` |
| `compute_risk_exposure` | `{positions}` | `{exposure_by_sector, exposure_by_market, var, source}` |
| `score_buy_signal` | `{fund_flow, news, technical}` | `{buy_score, action, confidence, evidence_strength}` |
| `suggest_rebalance` | `{positions, target_allocation}` | `{trades: [...], expected_improvement, confidence}` |
| `detect_concentration_risk` | `{positions}` | `{alerts: [...], risk_level}` |
| `compute_position_size` | `{symbol, account_value, risk_tolerance}` | `{suggested_size, kelly_fraction, confidence}` |

**关键差异(对比 Research)**:
- **强依赖 v1 portfolio_service**: 大部分工具直接复用 `PortfolioService.get_positions()` / `get_realized_pnl()` 等
- **输出常含建议动作**(rebalance / 加仓 / 减仓),需谨慎加 confidence
- **写操作**(`suggest_rebalance` 生成 trade 列表)需要 user confirmation 才能落地

**输入**: Portfolio Context(当前持仓 + 历史交易 + 用户风险偏好)

**输出**: `TaskResult` + 强建议动作

**失败处理**:
- 持仓数据缺失(`positions=[]`) → 返回 `holdings_empty` 提示,建议先录入交易
- 计算结果与用户风险偏好冲突 → `contradiction_score > 0.5`,提示用户确认

### 5.3 Monitoring Agent(监控) ⭐

**职责**: 每分钟扫描行情 + 新闻突发 + 异常资金流 → 触发 Alert。**从被动工具 → 主动系统的关键**。

**工具集**:

| Action | 输入 | 输出 |
|--------|------|------|
| `scan_market_anomaly` | `{tracked_symbols, threshold_pct}` | `{anomalies: [...], collected_at}` |
| `detect_news_burst` | `{keywords, lookback_min}` | `{bursts: [...], news_refs}` |
| `detect_fund_flow_anomaly` | `{symbols, threshold_value}` | `{anomalies: [...], source}` |
| `fire_alert` | `{type, severity, payload}` | `{alert_id, dispatched_via: [notify, ui, webhook]}` |
| `register_alert_rule` | `{rule_definition}` | `{rule_id, active: true}` |

**关键差异(对比 Research / Portfolio)**:
- **持续运行** — 不等待用户输入,通过 Event Bus 持续订阅 `market.update` / `news.collected` 事件
- **写操作可自动触发** — `fire_alert` 直接调 AlertDispatcher 推送通知(可配置为需要用户确认)
- **轻量级** — 每个监控周期 < 5 秒,避免阻塞主进程

**输入**: 事件流(Event Bus 订阅) + 监控规则(`alert_rules` 表)

**输出**: Alert 事件(`alert.fired`)→ 通过 Event Bus 广播

**失败处理**:
- 单次扫描失败 → 记录 `run_logs`,下一次扫描自动恢复
- Alert 推送失败(网络) → 重试 3 次,失败后只入 DB,不推送
- 误报率高 → Confidence Engine 自动降低同类 Alert 的 future priority

---

## 6. Event Bus

### 6.1 实现选型

| 阶段 | 选型 | 理由 |
|------|------|------|
| **v2 Phase 1** | **asyncio.Queue** | 单进程内足够,零依赖 |
| **v2 Phase 2+** | Redis pub-sub | 支持多进程 / 跨机器(Monitoring Agent 可独立部署) |

### 6.2 12 类事件

| 事件 | Payload | 触发方 |
|------|---------|--------|
| `task.created` | `{plan_id, task_id, agent, action}` | Orchestrator dispatch 启动 Task |
| `task.started` | `{plan_id, task_id, started_at}` | Agent.execute 开始 |
| `task.completed` | `{plan_id, task_id, status, duration_ms, result_summary}` | Agent.execute 完成 |
| `task.failed` | `{plan_id, task_id, error, retry_count}` | Agent.execute 抛异常 |
| `task.cancelled` | `{plan_id, task_id, reason}` | 用户中断 / 超时 |
| `evidence.collected` | `{symbol, evidence_keys, source, collected_at}` | EvidenceBuilder 写入 |
| `evidence.updated` | `{symbol, changed_fields, source}` | Scheduler 更新数据 |
| `market.update` | `{symbol, price, change_pct, source}` | Provider 推送新行情 |
| `news.alert` | `{symbols, headlines, importance}` | News 监测 |
| `alert.fired` | `{type, severity, title, body, source}` | Monitoring Agent 触发 |
| `portfolio.change` | `{account_id, symbol, type, qty, price}` | 用户录入交易 |
| `agent.memory.updated` | `{layer: short_term/strategy/market, scope, key}` | Memory 更新 |
| `user.command` | `{intent, params, source: chat/shortcut}` | UI 输入 |

### 6.3 统一 Envelope

```python
class Event(BaseModel):
    event_id: str                                # UUID
    event_type: str                              # 见上表
    timestamp: datetime                          # 事件时间
    source: str                                  # 事件来源 Agent / 模块
    correlation_id: str | None = None            # 关联的 plan_id / task_id(若有)
    payload: dict[str, Any]                      # 业务负载
```

### 6.4 订阅模式

```python
# 示例:Alert Panel 订阅 alert.fired
event_bus.subscribe("alert.fired", lambda event: send_to_electron(event))

# 示例:Monitoring Agent 订阅 market.update
event_bus.subscribe("market.update", lambda event: monitoring_agent.scan(event.payload))

# 示例:Confidence Engine 订阅 task.completed
event_bus.subscribe("task.completed", lambda event: confidence_engine.update(event.payload))
```

**关键约束**:
- 订阅者执行失败不应阻塞事件总线 → `try/except` + `loguru.warning` 兜底
- 同步 vs 异步订阅:Event Bus 统一 async,同步订阅者用 `asyncio.to_thread` 包裹
- 事件保留:`event_store` 表保留最近 7 天事件(供事后回溯)

---

## 7. Agent Memory 三层

### 7.1 三层划分

| 层 | 范围 | 存储后端 | TTL |
|----|------|---------|-----|
| **Short-term context** | 当前 Plan 内的 Task 间共享 | 内存 dict + (可选)SQLite 持久化 | Plan 结束即清除(或 24h 兜底) |
| **Strategy memory** | 用户偏好 + 历史决策(规则演化) | SQLite `agent_strategy_memory` 表(待 v2 Phase 2 新建) | 永久 |
| **Market memory** | 市场状态快照(每日收盘后冻结) | SQLite `agent_market_memory` 表(待 v2 Phase 2 新建) | 永久 |

### 7.2 Short-term Context

```python
class ShortTermMemory(BaseModel):
    plan_id: str
    user_intent: str
    upstream_results: dict[str, AgentResult]     # task_id → result
    intermediate_state: dict[str, Any]           # 任务间的中间状态(自由格式)
    created_at: datetime
    expires_at: datetime                         # TTL = plan_completed + 24h
```

**用途**:
- 同 Plan 内多个 Task 共享中间结果(如 t2 算完 fund_flow,t5 直接拿 `<from t2>` 占位符解析)
- Plan 崩溃后可恢复(从 SQLite 加载)

### 7.3 Strategy Memory

```python
class StrategyMemoryEntry(BaseModel):
    scope: str                                   # "user_preference" | "rule" | "feedback"
    key: str                                     # e.g. "user.risk_tolerance" / "rule.ma_cross_weight"
    value: Any                                   # 任意 JSON
    confidence: float = 0.5                      # 当前值的置信度(随反馈调整)
    last_updated: datetime
    feedback_history: list[FeedbackEvent] = []   # 历史反馈(调整依据)


class FeedbackEvent(BaseModel):
    feedback_id: str
    feedback_type: Literal["win", "loss", "neutral"]
    triggered_by: str                            # 触发反馈的事件
    old_confidence: float
    new_confidence: float
    timestamp: datetime
```

**示例**:
- `{"scope": "user_preference", "key": "max_position_size_pct", "value": 20, "confidence": 0.9}`
- `{"scope": "rule", "key": "ma_cross_weight", "value": 0.15, "confidence": 0.72}`(从初始 0.5 随反馈调整)

### 7.4 Market Memory

```python
class MarketMemorySnapshot(BaseModel):
    snapshot_date: date                          # 收盘日期
    market_regime: Literal["bull", "bear", "sideways", "volatile"]
    sector_rotation: dict[str, float]           # 板块轮动评分(板块 → 强度)
    volatility_index: float                      # VIX / 沪深300 波动率
    key_events: list[str]                        # 当日重大事件
    frozen_at: datetime                          # 冻结时间(每日 16:30 后)
```

**用途**:
- Planner 根据市场状态调整输出(如震荡市 → 推荐 watch 而非 buy)
- Research Agent 引用历史市场状态做"与昨日对比"

**冻结时机**: 每日 16:30(收盘 30 分钟后),Scheduler 触发冻结。

---

## 8. Confidence Engine

### 8.1 三指标定义

| 指标 | 定义 | 计算 | 范围 |
|------|------|------|------|
| **confidence** | AI 对自己输出的把握 | `0.5 + 0.3 * consistency + 0.2 * evidence_quality` | 0-1 |
| **evidence_strength** | 支撑证据的强度 | `min(1.0, evidence_count * 0.2 + source_diversity * 0.3 + recency_score * 0.5)` | 0-1 |
| **contradiction_score** | 与历史结论的矛盾度 | `weighted_avg(1 - cosine_similarity(this_result, historical_results))` | 0-1,越高越警示 |

### 8.2 各分项计算

```python
# 1. consistency: 该 Task 多次推理的结果一致性(如果有)
consistency = 1.0 - std_dev([r.action for r in self_replays[:5]])

# 2. evidence_quality: 证据来源权威性 + 数据新鲜度
evidence_quality = (
    0.4 * source_authority_score +  # 0-1
    0.3 * data_completeness_score +  # 0-1
    0.3 * recency_score                # 0-1
)

# 3. evidence_count: 引用的 Evidence 数量(归一化到 0-1,5 个以上为 1.0)
evidence_count = min(1.0, len(data_used) / 5)

# 4. source_diversity: 证据来源多样性(unique source 数 / 总 source 数)
source_diversity = len({d["source"] for d in data_used}) / max(1, len(data_used))

# 5. recency_score: 数据新鲜度(1h 内=1.0, 1d 内=0.7, 1w 内=0.4, > 1w=0.1)
def recency_score(collected_at: datetime) -> float:
    age_hours = (datetime.now() - collected_at).total_seconds() / 3600
    if age_hours < 1: return 1.0
    elif age_hours < 24: return 0.7
    elif age_hours < 168: return 0.4
    else: return 0.1
```

### 8.3 应用规则

| 指标 | 用途 |
|------|------|
| **confidence < 0.3** | 输出被标记为"低置信度",UI 显示 ⚠️ 图标,Research Agent 主动建议"证据不足" |
| **evidence_strength < 0.3** | 输出被标记为"证据薄弱",Planner 下次推理时引入更多上游 Task |
| **contradiction_score > 0.7** | 触发 Planner 重规划,把矛盾 Task 标记为"需用户确认" |
| **三指标全部 OK** | 输出正常,直接呈现给用户 |

### 8.4 反馈回路(Strategy Evaluator)

> 详见 [`architecture-v2.md`](architecture-v2.md) §7。

**离线任务**:`backend/agents/strategy_evaluator.py` 在每个交易日 20:30 运行,异步任务不阻塞主流程。

**胜 / 负判定规则**(显式、非 LLM 主观):
- **胜**: AI 给出的 action 在 N 天后被实际结果验证正确
  - `buy` → N 日内涨幅 > 阈值(默认 3%)
  - `sell` → N 日内跌幅 > 阈值
  - `watch` → N 日内无剧烈变化(±3% 内)
  - `avoid` → N 日内确实下跌
- **负**: 与上相反
- **平**: 幅度不够判定胜 / 负

**权重调整**:
- 胜 → `confidence += 0.05`(封顶 1.0)
- 负 → `confidence -= 0.10`(下限 0.0)
- 平 → 不调整

---

## 9. Tool 注册协议

### 9.1 Tool 接口

```python
class Tool(ABC):
    """所有 Tool 必须实现此接口。"""
    name: str                                    # 唯一名,如 "market.quote"
    description: str                             # 自然语言描述,供 LLM Planner 用
    input_schema: type[BaseModel]                # Pydantic 模型,声明输入参数
    output_schema: type[BaseModel]                # Pydantic 模型,声明输出

    @abstractmethod
    async def execute(self, params: dict, context: ToolContext) -> dict: ...

    @abstractmethod
    def get_required_auth(self) -> list[str]: ...  # 需要的权限 / API Key
```

### 9.2 Tool Registry

```python
# backend/agents/tools/registry.py
TOOL_REGISTRY: dict[str, Tool] = {}

def register(tool: Tool) -> Tool:
    TOOL_REGISTRY[tool.name] = tool
    return tool

# 使用示例
@register
class QuoteTool(Tool):
    name = "market.quote"
    description = "获取最新行情"
    input_schema = QuoteInput
    output_schema = QuoteOutput

    async def execute(self, params: dict, context: ToolContext) -> dict:
        # 委托给 v1 CollectionService
        return await context.collection_service.get_quotes(params["symbols"])

    def get_required_auth(self) -> list[str]:
        return []  # 读操作无需 auth
```

### 9.3 Tool Context

```python
class ToolContext(BaseModel):
    """Tool 执行时需要的上下文,由 Orchestrator 注入。"""
    api_key: str | None = None                   # X-API-Key(写 Tool 需要)
    collection_service: CollectionService        # v1 Service 引用
    news_service: NewsService
    portfolio_service: PortfolioService
    evidence_builder: EvidenceBuilder
    db: Connection                                # SQLite 连接(由 _WRITE_LOCK 保护)
    correlation_id: str                          # 关联 task_id / plan_id
```

### 9.4 鉴权传递

- **读 Tool**(如 `market.quote`、`news.search`)不需要 API Key
- **写 Tool**(如 `portfolio.record_trade`、`reports.generate`)需要 `X-API-Key` 验证
- Orchestrator 从 WebSocket / IPC 连接中提取 API Key,注入到 ToolContext
- Tool 内部不直接读 HTTP 头(单一入口 = Orchestrator)

### 9.5 审计与可观测性

每个 Tool 调用自动记录到 `raw_data` 表:

```python
{
    "tool_name": "market.quote",
    "input": {"symbols": ["hk00700"]},
    "output": {"quotes": [...]},
    "duration_ms": 234,
    "correlation_id": "plan-uuid-1234-task-t5",
    "source": "orchestrator",
    "data_type": "tool_call",
    "raw_json": "{...}",
    "collected_at": "2026-06-15T16:35:21+08:00"
}
```

---

## 附录 A:本设计文档引用的其他文档

- [`docs/v2/architecture-v2.md`](architecture-v2.md) — 6 层架构 + Electron 壳层
- [`docs/architecture-v2.drawio`](../architecture-v2.drawio) — 架构图
- [`docs/v1/architecture.md`](../v1/architecture.md) — v1 架构
- [`docs/v1/dev/lessons_learned.md`](../v1/dev/lessons_learned.md) — 23 条实操经验(继承 v1 写锁 / Evidence / Schema 约束)

## 附录 B:v2 Phase 1 实现优先级

| 组件 | Phase 1 范围 | 工作量 |
|------|--------------|--------|
| **Orchestrator 核心** | Agent 注册 + 任务分发(DAG) + 上下文传递 | 1 周 |
| **Event Bus(asyncio Queue)** | 12 类事件 + subscribe/publish API | 3 天 |
| **Planner Agent(规则型)** | 10+ 高频意图模板 + fallback | 1 周 |
| **Research Agent** | quote / kline / fund_flow / news 4 个核心 Tool + report 生成 | 2 周 |
| **Tool Registry** | 5 个核心 Tool 包装 + 鉴权传递 + 审计 | 1 周 |
| **Electron 壳层** | spawn FastAPI + 系统托盘 + 桌面通知 + 全局快捷键 | 1-2 周 |
| **Confidence Engine** | 三指标计算 + 反馈回路 v1(简版) | 1 周 |
| **总工作量** | v2 Phase 1 MVP | 8-10 周 |

## 附录 C:待 Phase 2+ 实现

- Portfolio Agent(依赖更多 v1 投资组合工具)
- Monitoring Agent(持续运行模式)
- Vector Memory(语义检索)
- Strategy Memory 完整演化
- LLM Planner(替换规则模板)
- electron-builder 打包
- Redis pub-sub(多进程支持)

---

> **本文档为 v2 设计稿,代码未启动。** 任何与代码现状冲突时,以代码为准。
