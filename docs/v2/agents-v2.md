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

### 2.2 Agent 注册表与统一抽象

> **架构修订说明(修订 1: Agent/Tool 严格分层)**: 早期设计把 `get_quote / get_kline / get_news / get_finance` 等"执行型 Tool"混入 Agent 的 `get_capabilities()`,导致 Agent 和 Tool 职责边界模糊。修正后,Agent 的 `capabilities` **只声明"思考型"动作**(如 `analyze_asset / generate_report`);"执行型"动作(`market.quote / news.search`)**全部下沉到 Tool Registry**。Agent 通过 `ctx.invoke_tool("market.quote", symbol=...)` 范式调用 Tool,Tool 不感知 Agent。

```python
# backend/agents/base.py
class TraceLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AgentState(str, Enum):
    """Agent 状态机 (修订: 统一抽象,所有 Agent 一致)。"""
    IDLE = "idle"
    PLANNING = "planning"
    AWAITING_TOOLS = "awaiting_tools"      # 等待 Tool 返回
    EXECUTING = "executing"                # 自身推理中
    SYNTHESIZING = "synthesizing"          # 整合多个 Tool 结果
    DONE = "done"
    FAILED = "failed"


class BaseAgent(ABC):
    """所有 4 个 Agent 的统一抽象。"""
    name: str                                # "research_agent" / "portfolio_agent" ...
    tools_used: list[str]                    # 声明式依赖, 例 ["market.quote","news.search"]
    capabilities: list[str]                  # 思考型动作, 例 ["analyze_asset","generate_report"]
    state: AgentState = AgentState.IDLE       # 状态机实例(修订: 显式建模)

    @abstractmethod
    async def plan(self, ctx: "Context") -> "Plan":
        """把 Task 拆成子计划 (可选, 简单 Task 可直接 execute)。"""
        ...

    @abstractmethod
    async def execute(self, ctx: "Context", plan: "Plan") -> "Result":
        """执行 Task, 通过 ctx.invoke_tool("market.quote", symbol=...) 调用 Tool。"""
        ...

    def on_state_enter(self, new_state: AgentState) -> None:
        """状态机钩子 (Orchestrator 驱动推进, Agent 自定义响应)。"""
        self.state = new_state

    async def emit_trace(
        self,
        ctx: "Context",
        level: TraceLevel,
        msg: str,
        data: dict | None = None,
    ) -> None:
        """分级 Trace 推送 — 修订 4: 默认仅 INFO+ 推送, DEBUG 留本地 buffer。"""
        if level == TraceLevel.DEBUG:
            ctx.trace_buffer.append({"level": level, "msg": msg, "data": data})
            return
        ctx.trace_buffer.append({"level": level, "msg": msg, "data": data})


# Orchestrator 注册表
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "planner": PlannerAgent,
    "research": ResearchAgent,
    "portfolio": PortfolioAgent,
    "monitoring": MonitoringAgent,
}
```

**关键约束**:
- **Agent = 思考**: `capabilities` 只列"思考型"动作(如 `analyze_asset`, 内部决定 *为什么* 调用哪些 Tool)
- **Tool = 执行**: 实际 IO 全部走 Tool Registry,Agent 不直接 `import` 任何 Provider/Service
- **声明式 + 命令式混合**: `tools_used` 声明名字(供依赖图分析),`ctx.invoke_tool` 命令式调用(运行时)
- **Tool 不知道 Agent**: Tool 只接收 `trace_id` 关联, 不持有 Agent 引用, 避免循环依赖
- **状态机由 Orchestrator 推进**: Agent 自身只暴露 `on_state_enter` 钩子, 不自己跳状态

### 2.3 任务分发算法(修订 3: Semaphore 资源控制)

> **架构修订说明(致命问题)**: 早期设计 `asyncio.create_task` 瞬间启动 1000+ 协程(500 个 stock × 2 task),导致 API 限流 + SQLite 锁竞争 + 内存暴涨。修订后:
> 1. **3 个 Semaphore** 包裹 dispatch 循环,按资源类型分层限流
> 2. 配合 §2.6 `validate_graph()` 严格校验,避免无效 plan 进入调度
> 3. 配合 §6 Policy Engine 的 `degrade_to: "reduce_concurrency"`,Runtime 动态调整 Semaphore

```python
# backend/agents/orchestrator.py
MAX_CONCURRENT_TASKS = 10     # 全局 Task 并发上限
MAX_CONCURRENT_LLM = 3        # LLM 调用并发上限 (防账单爆)
MAX_CONCURRENT_IO = 20        # Tool I/O 并发上限 (防 Provider 限流)

TASK_SEM = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
LLM_SEM = asyncio.Semaphore(MAX_CONCURRENT_LLM)
IO_SEM = asyncio.Semaphore(MAX_CONCURRENT_IO)


def _is_llm_action(action: str) -> bool:
    """判断 action 是否调用 LLM (Planner / LLM-judge 走 LLM_SEM, 其他走 IO_SEM)。"""
    return action.startswith("llm_") or action.endswith("_llm") or action in {
        "generate_research_report", "explain_market_move", "clarify_intent",
        "explain_pnl_attribution", "route_to_planner",
    }


async def dispatch(plan: TaskGraph) -> list[AgentResult]:
    """按依赖顺序 + 并行组并行执行 Task Graph, 配合 3 个 Semaphore。"""
    # 修订 2: dispatch 前先 validate
    validation = validate_graph(plan)
    if not validation.ok:
        raise InvalidPlan(validation.errors)

    completed: dict[str, AgentResult] = {}
    pending = {t.id: t for t in plan.tasks}
    in_flight: set[asyncio.Task] = set()

    while pending or in_flight:
        # 找出所有依赖已完成的任务
        ready = [
            t for t in pending.values()
            if all(dep in completed for dep in t.depends_on)
        ]
        # 并行启动所有 ready 任务, 按 action 类型分 Semaphore
        for task in ready:
            ctx = build_context(task, completed, plan)
            agent = AGENT_REGISTRY[task.agent]()
            sem = LLM_SEM if _is_llm_action(task.action) else IO_SEM

            async def _run_with_sem(task=task, ctx=ctx, agent=agent, sem=sem):
                # 双层 Semaphore: 任务级 (TASK_SEM) + 资源级 (sem)
                async with TASK_SEM, sem:
                    agent.on_state_enter(AgentState.EXECUTING)
                    result = await agent.execute(ctx, plan=await agent.plan(ctx))
                    agent.on_state_enter(AgentState.DONE)
                    return result

            in_flight.add(asyncio.create_task(_run_with_sem()))
            pending.pop(task.id)

        # 等待任意一个完成
        done, in_flight = await asyncio.wait(
            in_flight, return_when=asyncio.FIRST_COMPLETED
        )
        for t in done:
            result = t.result()
            completed[result.task_id] = result
            await event_bus.emit(Event(
                event_type="task.completed",
                payload=result.model_dump(),
            ))

    return list(completed.values())
```

**关键约束**:
- **TASK_SEM (10)**: 全局 Task 并发上限,保护内存
- **LLM_SEM (3)**: LLM 调用并发上限,防 DeepSeek 账单爆
- **IO_SEM (20)**: Tool I/O 并发上限,防 Provider 限流
- **双层 Semaphore**: 每个 Task 同时获取 TASK_SEM + (LLM_SEM 或 IO_SEM),严格串行化
- **§6 Policy Engine 可调低**: `degrade_to: "reduce_concurrency"` 改写 Semaphore 上限
- **§3.2 Task 加 `max_concurrency` 字段**: 特定 Task 可单独降低并发(默认用全局)

### 2.6 DAG 校验(修订 2: dispatch 前置)

> **架构修订说明(致命问题)**: 早期设计 `while pending or in_flight` 没校验环 / 孤儿节点 / 不存在依赖,会导致死循环 + 静默 bug。修订后:Orchestrator dispatch 前**必须**先 `validate_graph()`,校验失败直接 `InvalidPlan` 异常,不进入 dispatch。

```python
# backend/agents/orchestrator.py
class ValidationResult(BaseModel):
    ok: bool
    errors: list[str] = []            # 人类可读的错误列表
    warnings: list[str] = []          # 不致命, 仅提示


def validate_graph(plan: TaskGraph) -> ValidationResult:
    """3 类校验: 环 / 孤儿 / 不存在依赖。"""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 检查重复 task_id
    task_ids = [t.id for t in plan.tasks]
    if len(task_ids) != len(set(task_ids)):
        dup = [tid for tid in task_ids if task_ids.count(tid) > 1]
        errors.append(f"duplicate task ids: {set(dup)}")

    # 2. 检查依赖存在性 (修订 2: 不存在依赖 → 错误)
    for task in plan.tasks:
        for dep in task.depends_on:
            if dep not in task_ids:
                errors.append(f"task '{task.id}' depends on non-existent task '{dep}'")

    # 3. 检查环 (修订 2: 环 → 错误, 防死循环)
    if _has_cycle(plan.tasks):
        cycle = _find_cycle(plan.tasks)
        errors.append(f"cycle detected: {' -> '.join(cycle)}")

    # 4. 检查孤儿节点 (修订 2: 警告, 不致命)
    #    孤儿 = 无依赖也没被任何 task 依赖
    depended_by = {t.id: set() for t in plan.tasks}
    for t in plan.tasks:
        for dep in t.depends_on:
            depended_by[dep].add(t.id)
    orphans = [
        t.id for t in plan.tasks
        if not t.depends_on and not depended_by[t.id]
    ]
    if orphans:
        warnings.append(f"orphan tasks (no deps and no dependents): {orphans}")

    # 5. 检查 capability 与 agent 匹配 (修订 1 强化)
    for task in plan.tasks:
        agent_cls = AGENT_REGISTRY.get(task.agent)
        if agent_cls is None:
            errors.append(f"task '{task.id}' references unknown agent '{task.agent}'")
            continue
        # capability 必须在 agent.capabilities 里
        if task.action not in agent_cls.capabilities:
            errors.append(
                f"task '{task.id}' action '{task.action}' not in "
                f"agent '{task.agent}' capabilities: {agent_cls.capabilities}"
            )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def _has_cycle(tasks: list[Task]) -> bool:
    """DFS 检测环。"""
    graph: dict[str, list[str]] = {t.id: list(t.depends_on) for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {tid: WHITE for tid in graph}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in graph[u]:
            if color[v] == GRAY:
                return True  # 环
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[tid] == WHITE and dfs(tid) for tid in graph)


def _find_cycle(tasks: list[Task]) -> list[str]:
    """返回环路径(用于错误信息展示)。"""
    graph = {t.id: list(t.depends_on) for t in tasks}
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()

    def dfs(u: str) -> list[str] | None:
        path.append(u)
        path_set.add(u)
        for v in graph.get(u, []):
            if v in path_set:
                idx = path.index(v)
                return path[idx:] + [v]  # 环路径
            if v not in visited:
                r = dfs(v)
                if r:
                    return r
        path.pop()
        path_set.discard(u)
        visited.add(u)
        return None

    for tid in graph:
        if tid not in visited:
            r = dfs(tid)
            if r:
                return r
    return []
```

**关键约束**:
- **校验必须前置**: `dispatch(plan)` 第一行就是 `validate_graph(plan)`,失败立即抛 `InvalidPlan` 异常
- **校验 5 项**: 重复 task_id / 不存在依赖 / 环 / 孤儿(警告)/ capability 匹配(修订 1 强化)
- **不静默**: 校验失败必须明确报错,**不能默认 fallback**(会掩盖 bug)
- **§6 Policy Engine 不替代 validate_graph**: PolicyEngine 处理"运行时风险"(如市场状态),validate_graph 处理"plan 结构性错误",两者职责分离
- **测试覆盖**: 至少 5 个测试用例(无环/有环/孤儿/不存依赖/重复 ID),Phase 1 启动时落地

### 2.7 Async Workflow Engine(ChatGPT 第 2 轮:并发正确的位置)

> **架构修订(ChatGPT 第 2 轮反馈)**: "异步 ≠ Event Bus ≠ 多 Agent ≠ DAG"。并发应该发生在 **Workflow 和 Tool 层**,而不是把整个架构推到事件驱动。本节明确 Orchestrator dispatch 的并发范式 —— 在不丢掉 Task Graph 表达力的前提下,**用 `asyncio.gather` / `TaskGroup` 实现并行步骤**,而不是"步骤 A 完成 → 发 Event → 步骤 B 订阅 Event"。

#### 2.7.1 并发范式(伪代码)

**❌ 错误**:每步发 Event,下一个 Agent 订阅 Event

```python
# 错误:用 Event 串联步骤
await agent.step_a(ctx)
await event_bus.emit(Event(event_type="step.a.done", payload=result))
# step_b 必须订阅 step.a.done → 强耦合 + 顺序难调试
```

**✅ 正确**:Workflow 步骤直接 `asyncio.gather`,Task Graph 表达依赖

```python
async def analyze_user_intent(ctx: Context, plan: TaskGraph) -> PlanResult:
    """Workflow 步骤:并行获取 4 类数据 + LLM 综合。"""
    # 数据获取层:4 类 Tool 并发
    quote, kline, news, finance = await asyncio.gather(
        ctx.invoke_tool("market.quote", symbols=plan.symbols),
        ctx.invoke_tool("market.kline", symbols=plan.symbols, days=120),
        ctx.invoke_tool("news.search", symbols=plan.symbols, days=7),
        ctx.invoke_tool("finance.report", symbols=plan.symbols),
    )
    # LLM 综合层:综合 + 解释 并发(若综合 + 解释互不依赖)
    summary, risks = await asyncio.gather(
        llm_summarize(quote, kline, news, finance),
        llm_explain_risks(quote, kline, news, finance),
    )
    return PlanResult(summary=summary, risks=risks)
```

#### 2.7.2 性能对照(Research Agent 多数据并行)

**错误范式**(串行 IO):

```python
quote = await get_quote(symbols)       # 1s
kline = await get_kline(symbols)       # 1s
news = await get_news(symbols)         # 2s
finance = await get_finance(symbols)   # 1s
# 总计 ≈ 5s
```

**正确范式**(`asyncio.gather`):

```python
quote, kline, news, finance = await asyncio.gather(
    get_quote(symbols),
    get_kline(symbols),
    get_news(symbols),
    get_finance(symbols),
)
# 总计 ≈ max(1, 1, 2, 1) = 2s(节省 60%)
```

**多标的分析**(用户场景):

```python
# 用户输入:"帮我看看今天宁德时代能不能买,顺便看看黄金怎么样"
# Planner 生成 2 个并行 Task,Orchestrator 并发执行
await asyncio.gather(
    research_agent.execute(ctx_niatai, plan=plan_niaotai),
    research_agent.execute(ctx_gold, plan=plan_gold),
)
```

#### 2.7.3 Task Graph DSL 与 Workflow Engine 的关系

| 层 | 职责 | 表达什么 | 不表达什么 |
|----|------|---------|-----------|
| **Task Graph DSL** | 表达**依赖关系**(DAG) | 哪些 Task 可以并行 / 哪些必须串行 | 怎么并行(实现细节) |
| **Workflow Engine** | 表达**并发执行**(实现) | `asyncio.gather` / `TaskGroup` / Semaphore | 业务依赖 |

- Task Graph 描述 `t2 depends_on [t1]` —— **业务依赖**
- Workflow Engine 用 `await asyncio.gather(...)` —— **并发实现**
- 两者**解耦**:Task Graph 变了不需要改 Workflow Engine,反之亦然

#### 2.7.4 关键约束

- **Python 3.11+ 用 `asyncio.TaskGroup`**(自动异常传播 + 取消);3.10- 用 `asyncio.gather` + `return_exceptions=True`
- **步骤间共享 Context** 通过参数传递(不是 Event),保证数据流可追踪
- **Workflow 步骤不订阅 Event**:Workflow 内部步骤是 deterministic pipeline,Event 只在"外部触发器"(用户/定时器/告警)与 Workflow 入口之间
- **Performance Budget**:每个 Workflow 必须声明 `expected_duration_ms`,超过 1.5x 自动记录 `run_logs.warn`

### 2.4 上下文传递(修订 1 后: 移除直接 service 引用)

> **架构修订说明**: 原 §2.4 `AgentContext` 直接持有 `collection_service / news_service / portfolio_service / evidence_builder` 引用,绕过了 Tool Registry 抽象。修订后,AgentContext 只持有 `tool_registry` 引用,所有外部 IO 走 `ctx.invoke_tool("market.quote", symbol=...)` 范式。

```python
class Context:
    """Agent 执行上下文 (由 Orchestrator 注入)。"""
    plan_id: str
    task_id: str
    upstream_results: dict[str, "Result"]    # task_id -> Result
    evidence: dict
    short_term: dict
    market_state: "MarketState"             # Policy Engine 评估用
    trace_buffer: list[dict] = []           # 本地 buffer, 100ms flush
    tool_registry: "ToolRegistry"           # 唯一调用 Tool 的入口

    async def invoke_tool(self, name: str, **kwargs) -> "ToolResult":
        """声明式 Tool 调用, Tool 不知道是哪个 Agent。"""
        return await self.tool_registry.invoke(name, kwargs, trace_id=self.task_id)


def build_context(task: Task, completed: dict, plan: TaskGraph) -> Context:
    """为当前任务构造 Agent 上下文。"""
    return Context(
        plan_id=plan.plan_id,
        task_id=task.id,
        upstream_results={
            dep: completed[dep] for dep in task.depends_on if dep in completed
        },
        evidence=evidence_cache.get(task.params.get("symbol", "")),
        short_term=short_term_memory.get(task.id),
        market_state=current_market_state(),  # Policy Engine 评估需要
        tool_registry=TOOL_REGISTRY,
        trace_buffer=[],
    )
```

### 2.5 Thinking Trace 推送(修订 4: 分级 + 100ms 批量)

> **架构修订说明(致命问题)**: 100 task × 20 trace = 2000 个 IPC 消息,Electron 主进程会被 IPC 风暴打挂。修订后:
> 1. Trace 分 4 级 `DEBUG / INFO / WARNING / ERROR`,**默认只推 INFO+**
> 2. 批量推送:100ms flush 一次(不逐条 IPC)
> 3. Event Bus 新增 `thinking.trace.batched` 事件类型(承载批量 payload)

```python
class ThinkingTraceFlusher:
    """Agent 内部 emit_trace 写入 ctx.trace_buffer,
    100ms flush 一次到 Event Bus,避免 IPC 风暴。
    """
    def __init__(self, ctx: Context, event_bus: "AsyncEventBus"):
        self.ctx = ctx
        self.event_bus = event_bus
        self._last_flush = time.monotonic()
        self._flush_interval_ms = 100

    async def flush_if_due(self) -> None:
        now = time.monotonic()
        if (now - self._last_flush) * 1000 >= self._flush_interval_ms:
            await self.flush()

    async def flush(self) -> None:
        if not self.ctx.trace_buffer:
            return
        # DEBUG 级别留在本地, 不上 IPC
        shippable = [t for t in self.ctx.trace_buffer if t["level"] != "debug"]
        if shippable:
            await self.event_bus.emit(Event(
                event_id=str(uuid4()),
                event_type="thinking.trace.batched",
                timestamp=datetime.now(timezone.utc),
                source=self.ctx.task_id,
                correlation_id=self.ctx.plan_id,
                payload={"traces": shippable},
            ))
        self.ctx.trace_buffer.clear()
        self._last_flush = time.monotonic()


# Agent 内部使用示例
class ResearchAgent(BaseAgent):
    async def execute(self, ctx: Context, plan: Plan) -> Result:
        flusher = ThinkingTraceFlusher(ctx, event_bus)

        # DEBUG 级: 留本地, 不上IPC
        await self.emit_trace(ctx, TraceLevel.DEBUG, "starting execute",
                              data={"plan_id": ctx.plan_id})
        await flusher.flush_if_due()

        # INFO 级: 上 Event Bus
        await self.emit_trace(ctx, TraceLevel.INFO, "evidence_loaded",
                              data={"count": len(ctx.evidence)})
        await flusher.flush_if_due()

        # 调 Tool
        quote = await ctx.invoke_tool("market.quote", symbol="hk00700")

        # WARNING 级: 上 Event Bus (含原因)
        if quote is None:
            await self.emit_trace(ctx, TraceLevel.WARNING, "quote_unavailable",
                                  data={"symbol": "hk00700", "fallback": "latest_cached"})

        # ERROR 级: 立即 flush, 不等 100ms
        try:
            result = await self._synthesize(quote)
        except Exception as e:
            await self.emit_trace(ctx, TraceLevel.ERROR, "synthesize_failed",
                                  data={"error": str(e)})
            await flusher.flush()  # ERROR 立即 flush
            raise

        await flusher.flush()
        return result
```

**Renderer 端订阅**(`window.api.on('thinking.trace.batched', ...)`)批量显示在 Thinking Trace 面板。

**关键约束**:
- **DEBUG 永不上 IPC**: Agent 内部调试用, 留本地 buffer
- **INFO / WARNING / ERROR 上 Event Bus**: 批量 100ms flush 一次
- **ERROR 立即 flush**: 不等 100ms, 失败信号必须实时
- **flush_interval 100ms**: 经实测, 这是 Electron IPC 流畅 vs 实时性的最优折中

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
    action: str                                  # 该 Agent 能处理的 action 之一(在 agent.capabilities 中)
    params: dict[str, Any] = {}                  # 静态参数(不含依赖引用)
    inputs_mapping: dict[str, str] = {}          # 修订: 显式依赖引用, 替代 <from t1> 占位符
                                                     #   例 {"fund_flow": "t1.result.flows"}
    depends_on: list[str] = []                   # 依赖的 Task ID 列表
    priority: int = 5                            # 1(高) - 10(低),默认 5
    timeout_s: int = 30                          # 超时(秒)
    retry_on_failure: bool = False               # 失败是否自动重试(最多 1 次)
    max_concurrency: int | None = None           # 修订 3: 特定 Task 可单独降低并发(默认用全局 Semaphore)


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

**职责**: 聚合行情/财报/新闻/资金流 → 输出结构化研究报告。**只做事实,不做决策**(No-Opinion 原则)。

**内部架构(MapReduce 子线程并行抽取)**:

```
原始数据海(100+ 条新闻 / 50+ 财报)
        │
        ▼
[第 1 层:代码硬过滤]                ← 降噪 90% 杂音
  · 关键词匹配(标的代码 / 名称 / 行业标签)
  · 时间窗口裁剪(最近 N 天)
  · URL 去重 + 标题 normalize 去重
  · 来源权威性评分(westock > sina > RSS)
        │
        ▼
Top 候选(20-30 条)
        │
        ▼
[第 2 层:并行子线程抽取]            ← Map 阶段
  · 每条新闻/财报独立子任务
  · 抽取:实体(标的/人物/事件)、情感倾向(正/负/中)、关键数字(营收/同比/净利)
  · 输出结构化 Fact dict,不带主观词
        │
        ▼
[第 3 层:LLM 综合]                  ← Reduce 阶段
  · 输入:Top 10~15 Fact dict + Research Prompt(强制 No-Opinion)
  · 输出:结构化研究报告(只列事实 + 数据,不写"建议买入"等)
```

**关键约束**:
- **No-Opinion Prompt**: 严格禁止"建议买入/前景大好/值得关注"等主观词;只允许"近 3 日主力净流出 X 亿"、"技术面跌破半年线"等事实陈述
- **Token 控制**: 严禁把原始新闻全文喂给 LLM,必须先 Map 抽取 Fact dict(每条 ≤ 200 token),再 Reduce 综合
- **幻觉防御**: 所有 Fact 必须带 `source_url` + `collected_at`,LLM 输出时强制引用,不允许凭空生成数字

**工具集**(修订 1 后: capabilities 只列思考型动作):

| Capability(思考型) | 输入 | 输出 | tools_used(声明式依赖) |
|--------|------|------|---------|
| `analyze_asset` | `{symbol, days, dimensions}` | `{analysis: {...}, confidence}` | `["market.quote", "market.kline", "finance.report", "technical.compute"]` |
| `analyze_sector` | `{sector, limit, days}` | `{constituents: [...], flow_summary}` | `["sector.constituents", "market.fund_flow", "news.search"]` |
| `generate_research_report` | `{evidence_pack, dimensions}` | `{report: {...}, data_used}` | (无外部 IO,纯 LLM 综合) |
| `explain_market_move` | `{symbol, event_window}` | `{explanation: "...", evidence_refs}` | `["market.quote", "news.search", "news.sentiment"]` |
| `analyze_news_sentiment` | `{symbols, days}` | `{aggregated: {...}, breakdown}` | `["news.search", "news.sentiment"]` |
| `generate_risk_warning` | `{upstream_results}` | `{warnings: [...], risk_level}` | (无外部 IO) |
| `clarify_intent` | `{raw_intent, candidates}` | `{question: str}` | (无外部 IO) |

**输入**: 来自 Orchestrator 的 `AgentContext`(含上游 Evidence + 用户意图)

**输出**: `TaskResult`(`status="success"`, `result={...}`, `confidence`, `evidence_strength`)

**失败处理**:
- 单个 Tool 调用失败 → 标记 `status="failure"`,error_message,不影响 Plan 中其他 Task
- 多个上游结果矛盾 → `contradiction_score > 0.7`,Orchestrator 触发 Planner 重规划
- 关键 Tool(quote / kline)缺失 → 返回 `evidence_strength < 0.3`,Research Agent 主动建议"证据不足"
- 原始数据全部被代码过滤层拦截(0 条候选) → 返回 `{"status": "no_data"}`,提示用户扩大搜索窗口

### 5.2 Portfolio Agent(仓位智能体) ⭐

**职责**: 持仓分析 + 风险暴露 + 盈亏归因 + 仓位优化建议。**系统中最赚钱的 Agent**。

**双脑架构(Dual-Brain)**:

```
                ┌──────────────────────────────────────────┐
                │              Portfolio Agent              │
                │                                          │
用户输入 / 上游  │   ┌──────────────┐    ┌──────────────┐   │  最终输出
Research 报告 ───┼──▶│  左脑(量化)   │───▶│  右脑(LLM)   │───┼──▶ 调仓建议 + 解释
                │   │              │    │              │   │
                │   │  PyPortfolioOpt    │  仅做"翻译"  │   │
                │   │  Markowitz 模型    │  把数字变人话│   │
                │   │  Black-Litterman   │              │   │
                │   │  Barra 风险因子    │              │   │
                │   │  VaR / CVaR 计算   │              │   │
                │   └──────┬───────┘    └──────────────┘   │
                │          │                                │
                │          ▼                                │
                │   ┌──────────────────────────────────┐    │
                │   │   硬代码风控壁垒(代码层强制)     │    │
                │   │   · 单行业持仓上限 30%           │    │
                │   │   · 单标的持仓上限 20%           │    │
                │   │   · 最大回撤熔断 -15%           │    │
                │   │   · 杠杆率 ≤ 1.0                │    │
                │   │   ↓ LLM 推荐超出 → 直接截断     │    │
                │   └──────────────────────────────────┘    │
                └──────────────────────────────────────────┘
```

**硬代码风控壁垒(关键约束)**:

> **大模型算数学和仓位就是灾难。** LLM 只能负责**解释**和**参数设定**,核心的加减仓比例必须由 Python 量化代码强制约束。

| 约束项 | 阈值 | 行为 |
|--------|------|------|
| 单行业持仓上限 | 30% | LLM 推荐超出 → 截断到 30% + 警告"行业集中度风险" |
| 单标的持仓上限 | 20% | 同上 |
| 最大回撤熔断 | -15% | 触发 → 强制减仓 50%,即使 LLM 认为"只是技术调整" |
| 杠杆率上限 | 1.0 | 不允许杠杆,即使 LLM 强烈建议抄底 |
| 现金最低保留 | 5% | 保留流动性,避免满仓 |

**代码实现位置**: `backend/agents/portfolio/risk_guard.py`(独立模块,LLM 调用前 / 后双重校验)

**Capabilities(思考型动作, 修订 1 后)**:

| Capability(思考型) | 输入 | 输出 | tools_used(声明式依赖) |
|--------|------|------|---------|
| `analyze_holdings` | `{account_id?}` | `{positions, summary, attribution}` | `["portfolio.positions", "portfolio.pnl", "market.quote"]` |
| `compute_risk_exposure` | `{positions}` | `{exposure_by_sector, exposure_by_market, var}` | `["portfolio.positions"]` |
| `score_buy_signal` | `{fund_flow, news, technical}` | `{buy_score, action, confidence}` | (综合上游结果,无额外 IO) |
| `suggest_rebalance` | `{positions, target_allocation}` | `{trades, expected_improvement, risk_warnings}` | `["portfolio.positions", "market.quote"]` |
| `detect_concentration_risk` | `{positions}` | `{alerts, risk_level}` | `["portfolio.positions"]` |
| `compute_position_size` | `{symbol, account_value, risk_tolerance}` | `{suggested_size, kelly_fraction, confidence}` | `["portfolio.positions", "market.quote"]` |
| `explain_pnl_attribution` | `{attribution_data, days}` | `{narrative: "...", key_drivers}` | (无外部 IO,纯 LLM 解释) |

**关键差异(对比 Research)**:
- **强依赖 v1 portfolio_service**: 大部分工具直接复用 `PortfolioService.get_positions()` / `get_realized_pnl()` 等
- **输出常含建议动作**(rebalance / 加仓 / 减仓),需谨慎加 confidence
- **写操作**(`suggest_rebalance` 生成 trade 列表)需要 user confirmation 才能落地
- **依赖候选计算库**: `PyPortfolioOpt`(均值-方差 / Black-Litterman)、`pandas` / `numpy`(归因 / VaR)、可选 `riskfolio-lib`(更高级的因子模型)

**输入**: Portfolio Context(当前持仓 + 历史交易 + 用户风险偏好)

**输出**: `TaskResult` + 强建议动作(已被硬代码风控壁垒过滤)

**失败处理**:
- 持仓数据缺失(`positions=[]`) → 返回 `holdings_empty` 提示,建议先录入交易
- 计算结果与用户风险偏好冲突 → `contradiction_score > 0.5`,提示用户确认
- 风控壁垒触发 → 返回 `truncated_trades` + `risk_warning`,不静默截断

### 5.3 Monitoring Agent(监控) ⭐

**职责**: 每分钟扫描行情 + 新闻突发 + 异常资金流 → 触发 Alert。**从被动工具 → 主动系统的关键**。

**统一降噪策略(3 类输入各自 3 层过滤)**:

> **金融数据每分钟有无数异动**,如果每次异动都触发完整的多智能体流水线,API 账单会瞬间爆表。必须把 99% 的杂音在代码层拦掉。
>
> Monitoring Agent 接收 3 类输入:**行情流 / 资金流 / 新闻流**。每类输入都走"3 层漏斗"(硬规则 → 小模型 → 大模型裁判)。下面以**新闻流**为例展开(最复杂的输入),行情/资金流是它的简化版(详见 §5.3.2)。

#### 新闻流 3 层漏斗(详细版)

```
每天 10,000 条原始新闻(RSS + 财经媒体 + 微博/雪球/股吧)
        │
        ▼ 10000 → ~3000
┌────────────────────────────────────────────────────────────────┐
│ 第 1 层:硬规则层(纯代码,零模型成本)                          │
│  目标: 过滤 70% 低级噪音                                       │
├────────────────────────────────────────────────────────────────┤
│  · SimHash 去重:                                                │
│    金融媒体喜欢互相抄袭,同一条新闻换标题能发 20 遍              │
│    计算文本指纹(64-bit SimHash),海明距离 ≤ 3 → 直接丢弃        │
│    时间复杂度 O(N) → 单机可处理 10k+ 条/分钟                   │
│                                                                │
│  · Ticker Linking(股票池强绑定):                                │
│    维护主观测股池 / 概念股池(如 [新能源, 白酒, 半导体, ...])   │
│    用正则 + 基础 NER 匹配:                                      │
│      · 股票代码(hk00700 / sh600519 / usAAPL)                   │
│      · 公司简称(腾讯 / 茅台 / Apple)                            │
│      · 行业关键词(从 tracked_assets.tags 提取)                 │
│    通篇不含任何关注标的 / 板块 → 直接过滤                       │
│                                                                │
│  · 已知噪音模板(如"广告/推广/招贤纳士"):                       │
│    标题含特定关键词 → 直接丢弃                                  │
│                                                                │
│  · 时间窗口去重:同一 URL / 同一事件已处理过 → 跳过              │
└────────────────────────────────────────────────────────────────┘
        │
        ▼ ~3000 → ~500
┌────────────────────────────────────────────────────────────────┐
│ 第 2 层:小模型特征层(本地 FinBERT / DeBERTa-v3-small)        │
│  目标: 评估关联度 + 冲击力,过滤 80% 情绪噪音                   │
├────────────────────────────────────────────────────────────────┤
│  小模型不读懂逻辑,只判断 2 个指标:                             │
│                                                                │
│  · Relevance(关联度 0-1):                                       │
│    这则新闻对该公司的影响是边缘性的("公司赞助马拉松")           │
│    还是核心的("财报暴雷" / "大股东减持")                        │
│    → < 0.5 视为弱关联,即使后续冲击高也不触发                   │
│                                                                │
│  · Volatility Shock(波动冲击 0-1):                              │
│    新闻文本的情绪极性是否越过临界点                              │
│    极性: -1 (极度利空) ↔ +1 (极度利好)                         │
│    冲击: |极性| × 来源权威性                                    │
│                                                                │
│  · 规则拦截(关键):                                              │
│    ⚠️ 只有 shock_score > 0.75 时,这条新闻才有资格进入下一关    │
│    shock_score = abs(polarity) × source_authority × relevance  │
│                                                                │
│  · 候选模型(本地推理):                                          │
│    · FinBERT(金融专用,BERT-base,~440MB)                       │
│    · DeBERTa-v3-small(轻量,通用)                                │
│    · 自训小模型(基于历史 +feedback,Phase 2 评估)               │
└────────────────────────────────────────────────────────────────┘
        │
        ▼ ~500 → ~100-200
┌────────────────────────────────────────────────────────────────┐
│ 第 3 层:大模型裁判层(主智能体系统介入)                        │
│  目标: 判定"是否改变基本面 / 短期供需关系"                     │
├────────────────────────────────────────────────────────────────┤
│  此时每天 10000 条已被洗剩 100-200 条,大模型成本可承受        │
│                                                                │
│  · 大模型(Claude Sonnet / GPT-4o / DeepSeek-V3)只回答 1 个问: │
│    "这则新闻是否改变了该公司的核心基本面或短期供需关系?"        │
│                                                                │
│  · 判定结果:                                                    │
│    是 → 触发 Planner Agent 启动研究(进入主流水线)              │
│    否 → 直接归档(如"行业分析师表示看好未来发展"——纯主观)      │
│                                                                │
│  · 输出 Schema(强制 JSON):                                      │
│    {                                                            │
│      "fundamentally_changed": true,                             │
│      "change_type": "supply_shock" | "demand_shock" |           │
│                      "earnings_revision" | "policy_change" |    │
│                      "management_change" | "no_material_change",│
│      "confidence": 0.85,                                        │
│      "reasoning": "...",                                         │
│      "data_used": [<news_id>, <news_url>]                       │
│    }                                                            │
│                                                                │
│  · 批量优化:一次送 5-10 条新闻 → 单次 LLM 调用 →               │
│    减少 API 调用次数 + token 摊销                               │
└────────────────────────────────────────────────────────────────┘
        │
        ▼ ~100-200
Planner Agent 接收触发信号 → 启动主研究流水线
```

#### 行情流 / 资金流 3 层漏斗(简化版)

行情 / 资金流输入结构化(数值型),无需 SimHash / NER,简化为:

```
行情流(每分钟 N 个标的实时报价)
        │
        ▼
[第 1 层:硬规则] ← 拦截 95% 噪音(零成本)
  · 涨跌幅阈值(单标的 1h 内 ±5%)
  · 量比阈值(成交量 > 5 日均量 3 倍)
  · 跳空缺口(开盘 ±2% 缺口)
        │
        ▼
[第 2 层:统计特征] ← 拦截 4%
  · 滚动 z-score(1h 内价格偏离历史波动率 3σ)
  · 同业对比(板块内涨跌幅排名 Top/Bottom 5)
  · 资金流加权(主力净流入 > 板块平均 2 倍)
        │
        ▼
[第 3 层:大模型裁判] ← 仅 1% 启动主系统
  · 大模型判定:"这个异动是否由可解释的事件驱动(新闻/财报/公告)?"
  · 无事件驱动的异动 → 标记为"市场噪声",归档不告警
  · 有事件驱动 → 触发 Planner 联动 Research 找根因
```

**Alert Router 联动 Planner(关键范式)**:

当 Alert 触发时,**不直接弹窗**,而是向 Planner Agent 发送一个**隐式目标**(类用户输入),让 Planner 生成新的 Task Graph 评估应对方案。

```python
# Monitoring Agent → Planner Agent(隐式目标)
{
    "trigger": "新能源突发利空",
    "auto_task": "评估新能源持仓风险",
    "auto_intent": "我的新能源持仓在突发利空后,需要如何应对?",
    "severity": "high",
    "context": {
        "alert_id": "alert-uuid-5678",
        "related_symbols": ["sz002594", "sz300750"],
        "news_refs": ["url1", "url2"],
        "current_holdings": [{"symbol": "sz002594", "qty": 100, "cost": 250.0}],
        "current_pnl_pct": -3.2,
        "news_pipeline_stage": 3,           # 新闻流第 3 层漏斗输出
        "shock_score": 0.87,                 # 小模型打分
        "fundamental_change": "supply_shock"  # 大模型裁判结果
    }
}
```

Planner 接收后:
1. 解析 `auto_intent` 为 Task Graph(类似用户输入路径)
2. Orchestrator 调度 Portfolio Agent 评估 → Risk Guard 校验
3. 评估结果 + Alert 通知合并推送(避免用户被通知轰炸 + 还要单独查评估)

**Capabilities(思考型动作, 修订 1 后: 3 层漏斗 → 3 个 capability)**:

| Capability(思考型) | 输入 | 输出 | tools_used(声明式依赖) |
|--------|------|------|---------|
| `scan_market_anomaly` | `{tracked_symbols, threshold_pct}` | `{anomalies, collected_at}` | `["market.quote", "market.fund_flow"]` |
| `detect_news_burst` | `{raw_news, ticker_pool, macro_rules}` | `{layered_results, alerts}` | `["news.fetch", "news.macro_whitelist", "news.ticker_linking", "news.small_model_score", "news.llm_judge_batch"]` |
| `detect_fund_flow_anomaly` | `{symbols, threshold_value}` | `{anomalies, source}` | `["market.fund_flow"]` |
| `fire_alert` | `{type, severity, payload}` | `{alert_id, dispatched_via}` | `["alert.notify", "alert.webhook"]` |
| `route_to_planner` | `{auto_intent, severity, context}` | `{plan_id, dispatched}` | (无外部 IO, 内部 Orchestrator 路由) |
| `register_alert_rule` | `{rule_definition}` | `{rule_id, active}` | (无外部 IO, 写 alert_rules 表) |

**新闻漏斗 3 层 → Capability + Tool 映射(修订 1 后清晰化)**:

| 漏斗层 | 对应 Tool(执行型) | 触发 Capability |
|--------|------------------|----------------|
| **第 1 层硬规则** | `news.macro_whitelist`, `news.ticker_linking`, `news.simhash` | (Tool 自动执行,无 Capability) |
| **第 2 层小模型** | `news.small_model_score` | (Tool 自动执行) |
| **第 3 层 LLM 裁判** | `news.llm_judge_batch` | (Tool 自动执行) |
| **整体编排** | — | `detect_news_burst` Capability 协调 3 层 Tool |

**关键差异(对比 Research / Portfolio)**:
- **持续运行** — 不等待用户输入,通过 Event Bus 持续订阅 `market.update` / `news.collected` 事件
- **写操作可自动触发** — `fire_alert` / `route_to_planner` 直接调 AlertDispatcher 推送通知(可配置为需要用户确认)
- **轻量级** — 每个监控周期 < 5 秒,避免阻塞主进程
- **可独立部署** — 后期可拆为独立进程(Phase 2+),与 Orchestrator 通过 Redis 通信

**输入**: 事件流(Event Bus 订阅) + 监控规则(`alert_rules` 表)

**输出**:
1. Alert 事件(`alert.fired`)→ 通过 Event Bus 广播(供 UI 订阅)
2. 隐式目标(`route_to_planner`)→ Planner Agent(自动 Task Graph)

**失败处理**:
- 单次扫描失败 → 记录 `run_logs`,下一次扫描自动恢复
- Alert 推送失败(网络) → 重试 3 次,失败后只入 DB,不推送
- 误报率高 → Confidence Engine 自动降低同类 Alert 的 future priority
- route_to_planner 失败 → 退化为单纯 fire_alert,不丢告警

### 5.4 新闻流过滤层 — 算法细节与隐性关联兜底

> 本节是 §5.3 新闻流 3 层漏斗的算法实现细节。Phase 1 启动时按本文实现,Phase 2+ 可迭代优化。

#### 5.4.1 SimHash 文本指纹(第 1 层去重)

**原理**: 把文档分词 → 每个词映射到 64-bit hash → 加权向量求和 → 符号位输出指纹。

**算法**(Python 伪代码):

```python
def simhash(text: str, hashbits: int = 64) -> int:
    """计算文本的 SimHash 指纹。"""
    tokens = jieba.cut(text)                # 中文分词
    v = [0] * hashbits                      # 加权向量
    for token in tokens:
        h = mmh3.hash64(token)[0] & ((1 << hashbits) - 1)  # 64-bit hash
        for i in range(hashbits):
            v[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(hashbits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint

def hamming_distance(a: int, b: int) -> int:
    """海明距离:两个指纹不同的 bit 数。"""
    return bin(a ^ b).count("1")

def is_duplicate(news_hash: int, seen_hashes: list[int], threshold: int = 3) -> bool:
    """判断是否与已见新闻重复(海明距离 ≤ 3)。"""
    return any(hamming_distance(news_hash, h) <= threshold for h in seen_hashes)
```

**关键参数**:

| 参数 | 默认值 | 调整方向 |
|------|--------|---------|
| `hashbits` | 64 | 越多越精确但越慢;32 也可,误判率上升 |
| `threshold`(海明距离) | 3 | ≤ 3 判为重复;<5 判为相似;> 5 视为不同 |
| 窗口大小 | 24h | 24h 内的指纹参与对比;过期清理 |
| 来源分组 | 是 | 同源(如都来自新浪财经)去重阈值更严(≤ 2);跨源(新浪 vs RSS)放宽(≤ 3) |

**依赖库**: `jieba`(中文分词)+ `mmh3`(MurmurHash3,比 hashlib 更快)

**性能**: 10000 条/分钟 SimHash 计算 ≈ 5 秒(CPU i5 单核),完全够用。

#### 5.4.2 Ticker Linking 隐性关联兜底(关键补丁)

> **Gemini 指出的问题**: 国际新闻(如"某地发生战争")全文未提"黄金/石油",但战争 → 大宗商品上涨 → 影响持仓。如果第 1 层 Ticker Linking 只匹配标题/正文里出现的标的代码/简称,会漏掉这类**间接因果链**。
>
> 本节实现**双通道架构**:**(A) 宏观白名单无条件放行** + **(B) 因果规则图反向触发**。两条通道独立运行,任一命中即给新闻打标。

---

##### 通道 A:宏观核心词库白名单(无条件放行)

> **核心洞察**: 宏观大事(战争 / 加息 / CPI)全球每天最多几条,**放行它们不会让 Token 账单爆炸**,但能保住系统的**全局视野**——避免漏掉"中东冲突 → 原油 ETF"的致命盲区。

**白名单词库(初始版,可配置)**:

```python
# backend/agents/monitoring/config/macro_whitelist.py
MACRO_WHITELIST = [
    # 地缘政治
    "战争", "武装冲突", "军事行动", "地缘政治", "制裁", "禁运",
    "政变", "恐怖袭击", "核试验", "大使馆撤离",
    # 央行政策
    "美联储", "Fed", "FOMC", "欧洲央行", "ECB", "日本央行", "BOJ",
    "中国人民银行", "PBOC", "加息", "降息", "缩表", "扩表", "QE",
    # 宏观数据
    "CPI", "PPI", "非农", "就业数据", "GDP", "PMI", "通胀", "通缩",
    # 财政与贸易
    "关税", "贸易战", "贸易摩擦", "出口管制", "实体清单", "WTO",
    "财政赤字", "国债收益率", "美债",
    # 大宗商品与能源
    "OPEC", "欧佩克", "原油", "石油", "天然气", "黄金", "白银",
    "大宗商品", "期货", "商品交易所", "WTI", "Brent",
    # 汇率与跨境
    "汇率", "人民币贬值", "美元指数", "DXY", "跨境资本",
    # 系统性风险
    "金融危机", "银行倒闭", "主权债务违约", "主权评级下调",
    "经济衰退", "硬着陆", "软着陆",
]
```

**行为**:

```python
def macro_whitelist_check(news_text: str) -> bool:
    """只要新闻含白名单任一词,无条件放行 + 打标。"""
    matched = [kw for kw in MACRO_WHITELIST if kw in news_text]
    if matched:
        # 打 tag: macro_whitelist_pass=True + 命中的关键词列表
        return True, {"matched_keywords": matched}
    return False, {}
```

**关键约束**:

| 项 | 说明 |
|----|------|
| **放行范围** | 仅跳过第 1 层的 Ticker Linking + SimHash,**不跳过第 2 层 FinBERT** — 仍要算 relevance / shock_score |
| **打标字段** | `news.macro_whitelist_pass = True`, `news.macro_keywords = [kw1, kw2, ...]` |
| **白名单维护** | 写入 `config/macro_whitelist.py`,每月 review;用户偏好设置可禁用某些关键词 |
| **大小预估** | 初始 60-80 词,Phase 1 稳定后扩到 100-150 词 |
| **误判容忍** | 误判放行的边际成本 = 一条新闻走完漏斗 ≈ $0.0005(DeepSeek)→ 可忽略 |

**预期效果**:

```
每日 10000 条原始新闻
   ├─ Ticker Linking 命中: ~3000 条
   └─ Ticker Linking 漏掉: ~7000 条
        └─ Macro Whitelist 命中: ~5-20 条  ← 全球宏观大事
              └─ 给这 5-20 条打 macro_whitelist_pass=True
              └─ 与"反向因果命中"的条目合并 → 进入第 2 层
```

**与通道 B 的关系**:

- 通道 A 命中 → 不再走通道 B 的反向匹配(已确认宏观重要性)
- 通道 A 未命中 + 通道 B 命中 → 进入第 2 层(打 `macro_causal=true` 标签)
- 两者都没命中 → 视为"与持仓无关",第 1 层丢弃

---

##### 通道 B:因果规则图反向触发

```
原始因果规则图(handcrafted + 半自动挖掘):

[战争 / 地缘冲突]
    ├→ [原油上涨]          (原油 ETF, 能源股)
    ├→ [黄金上涨]          (黄金 ETF, 黄金股)
    └→ [避险情绪]          (美债, 防御板块)

[美联储加息]
    ├→ [科技股下跌]        (高估值科技)
    ├→ [银行股上涨]        (净息差扩大)
    └→ [新兴市场资本外流]  (港股, A 股)

[主要出口国限制出口]
    ├→ [对应商品价格上涨]  (粮食, 芯片, 稀土)
    └→ [下游成本上升]      (制造业)

... 50-100 条规则(覆盖 80% 常见宏观因果)
```

**实现方式**(3 选 1):

| 方案 | 复杂度 | 精度 | 推荐阶段 |
|------|--------|------|---------|
| **A. 关键词反向匹配**(Phase 1) | 低 | 中 | 标题/正文含"战争/加息/出口限制"等宏观词 → 触发因果规则图 → 反查影响的标的 |
| **B. Embedding 相似度**(Phase 2) | 中 | 高 | 把因果规则编码为 Embedding,新闻文本 Embedding 余弦相似 > 阈值 → 触发 |
| **C. 小模型 NER + 因果推理**(Phase 3) | 高 | 最高 | 用本地 LLM 1B-3B 抽取"事件 → 影响标的"对 |

**Phase 1 方案 A 实现**:

```python
MACRO_CAUSAL_RULES = {
    "战争|冲突|地缘|制裁": ["原油", "黄金", "国防", "美债"],  # 影响行业
    "加息|缩表|通胀": ["科技", "成长股", "银行", "美债"],
    "降息|宽松|QE": ["小盘股", "房地产", "黄金"],
    "出口限制|禁令|封锁": ["粮食", "芯片", "稀土", "对应下游制造业"],
    "汇率|贬值|本币": ["出口企业", "进口依赖型"],
}

def reverse_link(news_text: str, ticker_pool: set[str]) -> set[str]:
    """反向触发:从宏观关键词推断影响的行业/标的。"""
    matched_tickers = set()
    for macro_pattern, affected_sectors in MACRO_CAUSAL_RULES.items():
        if re.search(macro_pattern, news_text):
            for sector in affected_sectors:
                matched_tickers.update(SECTOR_TO_TICKERS.get(sector, []))
    return matched_tickers & ticker_pool
```

**关键约束**:
- 因果规则图必须**人工维护 + 定期 review**(每季度更新)
- 规则命中后,**不直接触发 Alert**,而是给该条新闻打上 `macro_causal=true` 标签,在第 2 层小模型打分时加权(降低 relevance 阈值)
- 用户可关闭某条规则(偏好设置)— 例如"我对黄金不感兴趣"

---

##### 双通道统一入口

```python
def layer1_filter(news_list: list[NewsItem], ticker_pool: set[str]) -> list[NewsItem]:
    """第 1 层硬规则:SimHash 去重 + 双通道宏观识别。"""
    # Step 1: SimHash 去重
    deduped = news_simhash_filter(news_list)
    
    # Step 2: 双通道识别(任一命中即保留)
    survived = []
    for news in deduped:
        # 通道 A: 宏观白名单无条件放行
        pass_a, info_a = macro_whitelist_check(news.text)
        
        # 通道 B: Ticker Linking + 因果规则反向触发
        linked_tickers = ticker_link(news.text, ticker_pool)
        pass_b = len(linked_tickers) > 0
        
        # 任一命中 → 进入第 2 层
        if pass_a or pass_b:
            news.macro_whitelist_pass = pass_a
            news.matched_keywords = info_a.get("matched_keywords", [])
            news.linked_tickers = linked_tickers
            news.macro_causal = pass_b and not pass_a  # 仅通道 B 命中时为 True
            survived.append(news)
    
    return survived
```

**漏斗指标修订**:

```
每日 10000 条原始新闻
   │
   ├─ SimHash 去重:                     10000 → ~8000 (~0.5s)
   │
   ├─ 通道 A 宏观白名单命中:            ~5-20 条  (放行 + 打 macro_whitelist_pass 标)
   │
   ├─ 通道 B Ticker Linking 命中:       ~3000 条
   │
   ├─ 通道 B 因果规则反向命中:          ~50-100 条 (打 macro_causal 标,降低后续阈值)
   │
   ├─ 合计进入第 2 层:                  ~3000-3200 条
   │
   ▼
[第 2 层 FinBERT 评分]                  3000 → ~600 条
   ├─ 通道 A 命中的 macro_whitelist_pass=True 新闻:
   │    shock_score 阈值放宽到 0.55(默认 0.75)— 宏观大事容错性更高
   │
   ▼
[第 3 层 LLM batch 裁判]                600 → ~150 条
   ▼
Planner 联动:                           ~150 → ~20 Alert/天
```

**对比修订前**:原来预期 ~15 Alert/天,现在因宏观白名单放宽阈值 → ~20 Alert/天(多出的 5 条主要是宏观大事)。**成本增加 < $0.10/天,可接受**。

#### 5.4.3 第 2 层小模型评分细节

**输入**: 第 1 层过滤后的候选新闻(每条约 500-2000 字)

**输出**: 3 个数值

```python
class NewsScore(BaseModel):
    relevance: float          # 0-1,关联度
    polarity: float           # -1 到 +1,情感极性(负=利空,正=利好)
    source_authority: float   # 0-1,来源权威性(westock > sina > 雪球 > 微博)
    shock_score: float        # 综合冲击分
    reasoning: str | None     # 小模型可解释性输出(可选)
```

**shock_score 计算**:

```python
shock_score = abs(polarity) * source_authority * relevance
```

**规则拦截**:`shock_score > 0.75` 才进入第 3 层。

**候选小模型**(本地推理,需 GPU 或量化 CPU):

| 模型 | 大小 | 速度(CPU) | 精度 | 备注 |
|------|------|----------|------|------|
| **FinBERT**(金融专用) | 440MB | 50ms/条 | 高 | 推荐 Phase 1 |
| DeBERTa-v3-base | 350MB | 40ms/条 | 中 | 通用,可二次微调 |
| Qwen2.5-1.5B-Instruct | 1.5GB | 200ms/条 | 高 | 可解释性好,带 reasoning |
| 自训小模型 | 50MB | 10ms/条 | 中 | Phase 2+ 反馈回路训练 |

**部署位置**: `backend/agents/monitoring/models/`(独立目录,模型文件 git LFS 或首次启动自动下载)

#### 5.4.4 第 3 层大模型裁判批量优化

**问题**: 100-200 条新闻如果一条一条送 LLM,每次 1k-2k token,总成本 ≈ 100-300k token/天,DeepSeek 也要几十元/天。

**批量优化策略**:

```python
def batch_judge(news_batch: list[NewsItem]) -> list[Judgment]:
    """一次 LLM 调用判断 5-10 条。"""
    prompt = build_batch_prompt(news_batch)  # 拼接 5-10 条新闻 + structured output
    response = llm.invoke(
        prompt,
        response_format={"type": "json_schema", "schema": BatchJudgmentSchema},
        temperature=0.1,  # 低温度,稳定输出
    )
    return parse_batch_judgment(response, news_batch)
```

**Batch Size 选择**:

| 场景 | Batch Size | 单次调用 Token | 每日总调用 |
|------|-----------|----------------|----------|
| 保守 | 3 | ~6k input + 1k output | ~33 次 |
| 推荐 | 5 | ~10k input + 2k output | ~20 次 |
| 激进 | 10 | ~20k input + 3k output | ~10 次 |

**成本估算**(DeepSeek-V3,假设 $0.14/M input + $0.28/M output):

| Batch | 每日成本(USD) | 每月成本(USD) |
|-------|-------------|--------------|
| 3 | ~$0.05 | ~$1.5 |
| 5 | ~$0.08 | ~$2.4 |
| 10 | ~$0.13 | ~$3.9 |

**结论**: 第 3 层批量调用成本可承受(每月 < $5),关键是把第 1 + 2 层做好,确保进入第 3 层的都是真信号。

**JSON Schema(强制)**:

```python
class BatchJudgmentSchema(BaseModel):
    judgments: list[SingleJudgment]

class SingleJudgment(BaseModel):
    news_id: str
    fundamentally_changed: bool
    change_type: Literal[
        "supply_shock",        # 供给冲击(原材料 / 产能 / 出口限制)
        "demand_shock",        # 需求冲击(订单 / 消费 / 出口)
        "earnings_revision",   # 盈利预测大幅修正
        "policy_change",       # 政策变化(行业政策 / 监管)
        "management_change",   # 管理层 / 大股东变动
        "no_material_change",  # 无实质影响(分析师废话等)
    ]
    confidence: float           # 0-1,大模型对自己判断的把握
    reasoning: str              # 1-2 句话解释
    affected_symbols: list[str] # 影响的标的(可多个)
```

**防御性约束**(继承 v1 lessons_learned §17):
- 大模型 API 调用必须经过 `conftest.py` 拦截保护(防止真实 API 调用泄漏成本)
- 输入 / 输出 loguru 不打印完整 prompt(只打印 token 数 + 摘要)
- `temperature ≤ 0.2`(确保输出一致性)
- 失败重试最多 1 次,失败后该批次直接归档为"未知"

#### 5.4.5 端到端漏斗性能预算(含双通道宏观识别)

```
每日 10000 条原始新闻
   │
   ├─ 第 1 层 SimHash 去重:               10000 → 8000 (~0.5s)
   │
   ├─ 第 1 层 通道 A 宏观白名单命中:      ~10-30 条 (无条件放行 + 打 macro_whitelist_pass 标)
   │
   ├─ 第 1 层 通道 B Ticker Linking:      8000 → ~3000 条
   │
   ├─ 第 1 层 通道 B 因果规则反向命中:    ~50-100 条 (打 macro_causal 标)
   │
   ├─ 合计进入第 2 层:                    ~3000-3200 条
   │
   ├─ 第 2 层 FinBERT 小模型:             3200  → 500-600 (~150s)
   │    (并行 4 进程,实际 ~40s)
   │    ⚠️ 通道 A 命中的新闻: shock_score 阈值放宽到 0.55(默认 0.75)
   │
   ├─ 第 3 层大模型批量:                  500-600 → 100-200 (~120s)
   │    (batch=5, ~25 次调用)
   │
   └─ 触发 Planner 联动:                  100-200 个事件 → 评估后触发 15-25 次 Planner
        │
        ▼
       ~20 个 Alert / 天(用户实际收到)
       其中 ~5 条来自宏观白名单通道(全球大事),~15 条来自常规标的新闻

成本预算:
- SimHash: $0(本地计算)
- FinBERT: $0(本地推理)
- 大模型批量: ~$0.10 / 天(略增,因双通道多放 ~50 条进漏斗)
- LLM 触发 Planner: ~$0.05 / 次 × 20 = $1.00 / 天

日总成本: ~$1.10 / 天(可接受)
```

---

## 7. Event Bus

### 7.1 实现选型 + 边界划分(ChatGPT 第 2 轮反馈)

| 阶段 | 选型 | 理由 |
|------|------|------|
| **v2 Phase 1** | **Observer Pattern**(订阅者 set + `asyncio.gather` 广播) | 真正的 Pub-Sub,支持多订阅者并发接收;零依赖 |
| **v2 Phase 2+** | Redis pub-sub | 支持多进程 / 跨机器(Monitoring Agent 可独立部署) |

> **架构修订说明**: 原设计 §6.1 选用 `asyncio.Queue`,但 `asyncio.Queue` 是点对点(单消费者)而非 Pub-Sub(多消费者广播),会导致 Monitoring Agent 和 Confidence Engine 同时订阅 `task.completed` 时事件被随机分发给其中一个。修正为 Observer Pattern,见 [§7.2](#72-event-bus-实现细节)。
>
> **第二轮修订(ChatGPT 反馈)**: "Event-Driven ≠ Everything Is Event"。本节区分 **Domain Event**(走 Event Bus)与 **Internal Call**(直接函数调用),避免事件系统膨胀到不可维护的程度。

### 7.2 Domain Event vs Internal Call 边界

**核心原则**:Event Bus 只承载**跨模块通知**,不承载**模块内部状态变更**。

| 类别 | 处理方式 | 例子 |
|------|---------|------|
| **Domain Event**(走 Event Bus) | 跨模块 / 跨层通知;用户/定时器/市场/外部消息产生 | `user.command`, `timer.news_collect`, `market.anomaly`, `alert.fired` |
| **Internal Call**(直接函数) | 模块内部状态变更;记忆、置信度、缓存、Context 流转 | Memory 更新、Confidence 计算、Tool 执行结果返回、Task 上下文传递 |

**判定规则**: 问 3 个问题——

1. 通知对象在**不同模块 / 不同层**吗? → 是 → Domain Event
2. 事件消费者**不固定 / 会动态增减**吗? → 是 → Domain Event
3. 仅是**模块内部状态写入**吗? → 是 → Internal Call(`memory.update(...)`、`confidence.record(...)` 等)

> **反例**(已删除): `agent.memory.updated`、`tool.executed`、`task.context.changed`、`confidence.updated`、`strategy.updated` —— 全部改为 Internal Call。原因是:这些事件的"订阅者"通常就是触发者本身,绕一圈反而把"谁改了 Memory"变成不可追溯的问题。

### 7.3 10 类核心 Domain Event

| # | 事件 | Payload | 触发方 | 订阅方 |
|---|------|---------|--------|--------|
| 1 | `user.command` | `{intent, params, source: chat\|shortcut\|tray}` | UI(Chat / Command Palette / Tray 菜单) | Orchestrator |
| 2 | `timer.news_collect` | `{trigger_at}` | APScheduler(60min) | NewsService → 后续 Monitoring 订阅 |
| 3 | `timer.market_scan` | `{trigger_at, symbols}` | APScheduler(15min) | Monitoring Agent |
| 4 | `timer.ai_report` | `{trigger_at, schedule: daily\|weekly}` | APScheduler(每日 20:00) | Orchestrator → Planner |
| 5 | `timer.cleanup` | `{trigger_at, retention_days}` | APScheduler(每日 03:30) | Storage Cleanup Job |
| 6 | `market.anomaly` | `{symbol, change_pct, volume_ratio, source}` | Monitoring Agent(硬规则层) | Orchestrator → Planner(隐式目标) |
| 7 | `news.breaking` | `{news_id, shock_score, macro_causal, macro_whitelist_pass, linked_tickers}` | Monitoring Agent(第 3 层 LLM 裁判) | Orchestrator → Planner(隐式目标) |
| 8 | `fundflow.anomaly` | `{symbol, net_flow, threshold, source}` | Monitoring Agent | Orchestrator → Planner(隐式目标) |
| 9 | `portfolio.changed` | `{account_id, symbol, type, qty, price, source: user\|tool}` | 用户录入交易 / Portfolio Tool 写入 | Confidence Engine(可选) / UI Refresh |
| 10 | `alert.fired` | `{alert_id, type, severity, title, body, source, related_symbols}` | Monitoring / Portfolio Agent | Electron 主进程 → 桌面通知 + UI Alert Panel |
| 11 | `plan.completed` | `{plan_id, user_intent, status, final_output_ref}` | Orchestrator dispatch 全部结束 | UI(摘要推送) / Memory(可选) |

> **删除清单**(对比第一版 13 类):
> - `task.created / task.started / task.completed / task.failed / task.cancelled` → 改为 Internal Call(Orchestrator 内部 + UI 通过 IPC 推送)
> - `evidence.collected / evidence.updated` → 改为 Internal Call(EvidenceBuilder 直接返回)
> - `agent.memory.updated` → 删除(Memory 内部状态)
> - `user.command` 保留(用户跨层入口)

**事件总线作为"模块间的神经系统"**,而不是"所有代码的血液循环系统"——避免后期订阅爆炸 / 循环依赖。

### 7.4 统一 Envelope

```python
class Event(BaseModel):
    event_id: str                                # UUID
    event_type: str                              # 见 §7.3 表
    timestamp: datetime                          # 事件时间
    source: str                                  # 事件来源 Agent / 模块
    correlation_id: str | None = None            # 关联的 plan_id / alert_id(若有)
    payload: dict[str, Any]                      # 业务负载
```

### 7.5 订阅模式

```python
# 示例:Alert Panel 订阅 alert.fired
event_bus.subscribe("alert.fired", lambda event: send_to_electron(event))

# 示例:Monitoring Agent 订阅 market.anomaly
event_bus.subscribe("market.anomaly", lambda event: monitoring_agent.scan(event.payload))

# 示例:Orchestrator 订阅 timer.ai_report
event_bus.subscribe("timer.ai_report", lambda event: orchestrator.handle_scheduled(event.payload))
```

**关键约束**:
- 订阅者执行失败不应阻塞事件总线 → `try/except` + `loguru.warning` 兜底
- 同步 vs 异步订阅:Event Bus 统一 async,同步订阅者用 `asyncio.to_thread` 包裹
- **事件保留**:`event_store` 表保留最近 7 天事件(供事后回溯)
- **不准订阅 Internal Event**:Domain/Internal 边界由 lint 规则 + 文档强制,代码评审时检查

---

## 8. Agent Memory 三层

### 8.1 三层划分

| 层 | 范围 | 存储后端 | TTL |
|----|------|---------|-----|
| **Short-term context** | 当前 Plan 内的 Task 间共享 | 内存 dict + (可选)SQLite 持久化 | Plan 结束即清除(或 24h 兜底) |
| **Strategy memory** | 用户偏好 + 历史决策(规则演化) | SQLite `agent_strategy_memory` 表(待 v2 Phase 2 新建) | 永久 |
| **Market memory** | **市场事实快照**(每日收盘后冻结,不含状态标签) | SQLite `agent_market_snapshot` 表(待 v2 Phase 2 新建) | 永久 |

### 8.2 Short-term Context

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

### 8.3 Strategy Memory

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

### 8.4 Market Memory(只存事实,不存状态标签)

> **架构修订(ChatGPT 第 2 轮反馈)**: 旧设计把市场冻结为 `bull / bear / sideways / volatile` 4 种状态——这种分类**一定会分类错、状态漂移、维护困难**。AI 完全能自己判断市场状态,Memory 不应该承担"打标签"的职责。改为**只存事实数据**(`MarketSnapshot`),不存任何主观标签。

```python
class MarketSnapshot(BaseModel):
    """每日收盘后冻结的市场事实,不含状态标签。"""
    snapshot_date: date                          # 收盘日期
    index_levels: dict[str, float]              # {"HSI": 18500, "SPX": 5400, "CSI300": 3500}
    volatility_index: float                      # VIX / 沪深300 波动率(数值,非标签)
    sector_performance: dict[str, float]         # 板块 → 当日涨跌幅(数值)
    key_events: list[str]                        # 当日重大事件(描述,非分类)
    frozen_at: datetime                          # 冻结时间(每日 16:30 后)
```

**用途**:
- Planner 推理时**自己**根据数据判断市场状态(如 `vix > 25` → 警惕),不依赖预置标签
- Research Agent 引用历史 Snapshot 做"与昨日对比"(`index_levels["HSI"]` 对比)
- 用户可在 UI 中查看历史 Snapshot,但**绝不显示**"当前是牛市"这种分类标签

**冻结时机**: 每日 16:30(收盘 30 分钟后),Scheduler 触发冻结。

---

## 9. Confidence Engine

> **架构修订(ChatGPT 第 2 轮反馈)**: 旧设计 `confidence=0.8134` 等浮点数属于 **Pseudo Precision(伪精确)**——金融领域对 `0.82` 的解读会过度,而实际并无真实统计意义。改为 **LOW / MEDIUM / HIGH 三档 + Evidence 强 / 中 / 弱** 二维评估,既符合用户认知习惯,又避免 Pseudo Precision。

### 9.1 二维评估框架

#### 9.1.1 Confidence(模型对输出的把握)

| 档位 | 含义 | 触发条件 |
|------|------|---------|
| **HIGH** | AI 对输出**有把握**,可直接采纳 | 模型多次推理一致(consistency ≥ 0.8)+ 证据完整(evidence_strength ≥ 0.7) |
| **MEDIUM** | AI 倾向该输出,但**有保留** | 一致性中(0.5-0.8)或证据中等(0.4-0.7) |
| **LOW** | AI **不确定**,需用户谨慎采纳 | 一致性低(< 0.5)或证据薄弱(< 0.4),Research Agent 主动建议"证据不足" |

```python
class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
```

**档位计算(伪代码,非公式)**:

```python
def compute_confidence(
    consistency: float,        # 0-1, 多次推理一致性
    evidence_strength: float,  # 0-1, 见 §9.1.2
) -> Confidence:
    score = 0.5 * consistency + 0.5 * evidence_strength
    if score >= 0.75:
        return Confidence.HIGH
    elif score >= 0.5:
        return Confidence.MEDIUM
    else:
        return Confidence.LOW
```

> **关键约束**: `Confidence` 是**枚举,不是浮点数**。UI 显示徽章颜色(绿/黄/红),不用数字。

#### 9.1.2 Evidence Strength(支撑证据强度)

| 档位 | 含义 | 触发条件 |
|------|------|---------|
| **STRONG** | 证据**充分**,多源 + 新鲜 | ≥ 3 个 unique 来源 + 数据 1 天内 + 数据完整度 ≥ 0.8 |
| **MEDIUM** | 证据**基本可用**,单源或稍旧 | 2 个 unique 来源 + 数据 1 周内 |
| **WEAK** | 证据**不充分**,单源或过期 | 1 个来源或数据 > 1 周 |

```python
class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
```

**档位计算(伪代码)**:

```python
def compute_evidence_strength(
    data_used: list[dict],     # [{source, type, collected_at}, ...]
) -> EvidenceStrength:
    unique_sources = {d["source"] for d in data_used}
    recency_h = min(age_hours(d["collected_at"]) for d in data_used)
    completeness = min(1.0, len(data_used) / 5)  # 5 个为满

    if len(unique_sources) >= 3 and recency_h < 24 and completeness >= 0.8:
        return EvidenceStrength.STRONG
    elif len(unique_sources) >= 2 and recency_h < 168:
        return EvidenceStrength.MEDIUM
    else:
        return EvidenceStrength.WEAK
```

### 9.2 应用规则

| Confidence | Evidence | UI 显示 | Orchestrator 行为 |
|------------|----------|---------|------------------|
| HIGH | STRONG | ✅ 绿色徽章 | 直接呈现给用户 |
| HIGH | MEDIUM | ✅ 绿色徽章 + 注释"证据 1 来源" | 直接呈现 |
| MEDIUM | * | ⚠️ 黄色徽章 | 直接呈现 + 建议"参考即可" |
| LOW | * | 🔴 红色徽章 + "证据不足" | **强制** 用户确认才呈现 |
| * | WEAK | (不影响 Confidence,但)Research Agent 主动声明 | 触发 Planner 引入更多上游 Task |

**contradiction_score 保留(浮点 0-1)** —— 用于内部判定矛盾度,不暴露给用户。

### 9.3 反馈回路:离线 Strategy Evaluator(严禁在线学习)

> **架构修订(ChatGPT 第 2 轮反馈)**: 旧设计 "AI 建议 → 市场验证 → 自动 `confidence += 0.05`" 是 **在线学习系统**——金融市场是**非平稳系统**,今天有效明天失效,会导致 **策略漂移 / 越学越差**。改为**离线 + 用户确认**,记录评估结果但**不自动调整参数**。

#### 9.3.1 离线任务

**触发**:`backend/agents/strategy_evaluator.py` 在每个交易日 **20:30** 运行,异步任务不阻塞主流程。

**输入**:`agent_runs` 表(待 v2 Phase 1 新建)+ `ai_reports` 表 + 同期实际行情数据。

**输出**:**离线评估报告**(`strategy_evaluations` 表),包括:
- 每条历史 AI 建议的胜 / 负 / 平判定
- 各 Confidence 档位的实际命中率(用于**人工 review**,不写回 confidence 算法)
- 异常样本(连续 3 次"买"建议后 7 天内跌 > 10%)

#### 9.3.2 胜 / 负判定规则(显式,非 LLM 主观)

| AI action | 胜 | 负 | 平 |
|-----------|----|----|----|
| `buy` | N 日内涨幅 > 阈值(默认 3%) | N 日内跌幅 > 阈值 | 幅度不够 |
| `sell` | N 日内跌幅 > 阈值 | N 日内涨幅 > 阈值 | 幅度不够 |
| `watch` | N 日内无剧烈变化(±3%) | 涨/跌 > 5% | 3-5% 区间 |
| `avoid` | N 日内确实下跌 | 上涨 | 幅度不够 |

#### 9.3.3 严禁的"在线自动调权"

| ❌ 禁止 | ✅ 替代 |
|--------|--------|
| AI 反馈后自动 `confidence += 0.05` | 写入离线报告,**人工 review 后** 由用户在 Settings 手动调整 |
| 自动调整规则权重 | 写入反例样本,人工加入规则库 |
| 自动改写 confidence 计算公式 | 人工 review + 文档更新 + commit |

**Why**: 金融市场非平稳 → 在线学习会策略漂移 → 越学越差。所有权重调整必须**人工 review**。

#### 9.3.4 反馈回路图

```
AI 输出 (含 Confidence / Evidence)
   ↓
写入 ai_reports + agent_runs
   ↓
N 天后(默认 7)
   ↓
Strategy Evaluator (离线 20:30 跑)
   ↓
生成 strategy_evaluations 报告(人工查看,不写回)
   ↓
人工 review
   ├─ 发现系统性问题 → 改规则 / 改 Prompt / 改代码
   └─ 正常 → 不动参数
```

**绝无自动回路**。

---

## 10. Tool 注册协议(修订 1 展开: 完整 Tool Registry 章节)

### 10.1 Tool 接口(修订 1 强化: 工具是执行单元, 不含思考)

```python
class Tool(ABC):
    """所有 Tool 必须实现此接口。"""
    name: str                                # "market.quote" — 命名空间.动作
    version: str = "1.0.0"
    description: str                         # 自然语言描述, 供 LLM Planner 选 Tool
    required_scopes: list[str]               # ["read"] / ["write"] / ["confirm"]
    input_schema: type[BaseModel]            # Pydantic 模型, 严格类型
    output_schema: type[BaseModel]           # Pydantic 模型

    @abstractmethod
    async def run(self, **kwargs) -> "ToolResult": ...

    def get_required_auth(self) -> list[str]:
        return self.required_scopes
```

**关键约束(修订 1 强化的分层原则)**:
- **Tool 不感知 Agent**: 只接收 `trace_id` 关联, 不持有 Agent 引用
- **Tool 不知道调用方 Agent**: 避免循环依赖
- **Tool 是执行型, 不含思考**: 内部不调 LLM, 不做"分析", 只返回原始 IO 结果
- **输入输出强类型**: 避免 `dict[str, Any]` (与 TaskGraph 的 inputs_mapping 配合, 见 §3.2)

### 10.2 Tool Registry(修订 1: 单一注册入口)

```python
# backend/agents/tools/registry.py
TOOL_REGISTRY: dict[str, "Tool"] = {}

def register(tool: "Tool") -> "Tool":
    TOOL_REGISTRY[tool.name] = tool
    return tool


class ToolRegistry:
    """唯一对外暴露的 Tool 调用入口, Agent 通过 ctx.invoke_tool() 走这里。"""
    def __init__(self) -> None:
        self._tools: dict[str, "Tool"] = {}

    def register(self, tool: "Tool") -> None:
        self._tools[tool.name] = tool

    async def invoke(
        self,
        name: str,
        kwargs: dict,
        trace_id: str,
        session_scopes: list[str] = ["read"],
    ) -> "ToolResult":
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFound(f"Tool '{name}' not registered")
        # 鉴权: 比对 session_scopes 与 tool.required_scopes
        if not set(tool.required_scopes).issubset(set(session_scopes)):
            raise InsufficientScope(
                f"Tool '{name}' requires {tool.required_scopes}, "
                f"session has {session_scopes}"
            )
        # 强类型校验 kwargs
        validated = tool.input_schema(**kwargs)
        # 调用
        result = await tool.run(**validated.model_dump())
        # 审计: 入 raw_data
        await self._audit(tool.name, kwargs, result, trace_id)
        return result

    async def _audit(self, name, kwargs, result, trace_id) -> None:
        # 写入 raw_data 表, 与 v1 一致
        ...


# 使用示例
@register
class QuoteTool(Tool):
    name = "market.quote"
    description = "获取最新行情"
    required_scopes = ["read"]
    input_schema = QuoteInput
    output_schema = QuoteOutput

    async def run(self, symbols: list[str]) -> dict:
        # 委托给 v1 CollectionService
        return await collection_service.get_quotes(symbols)
```

### 10.3 Tool 目录组织(按 namespace 划分)

```
backend/agents/tools/
├── __init__.py
├── registry.py                      # ToolRegistry 单例
├── market/
│   ├── quote.py                     # market.quote
│   ├── kline.py                     # market.kline
│   ├── fund_flow.py                 # market.fund_flow
│   └── limit_depth.py
├── news/
│   ├── fetch.py                     # news.fetch (拉原始)
│   ├── search.py                    # news.search (关键词)
│   ├── sentiment.py                 # news.sentiment (情感分析)
│   ├── macro_whitelist.py           # news.macro_whitelist
│   ├── ticker_linking.py            # news.ticker_linking
│   ├── simhash.py                   # news.simhash
│   ├── small_model_score.py         # news.small_model_score
│   └── llm_judge_batch.py           # news.llm_judge_batch
├── finance/
│   ├── report.py                    # finance.report
│   ├── indicator.py                 # finance.indicator
│   └── holder.py                    # finance.holder
├── portfolio/
│   ├── positions.py                 # portfolio.positions (read)
│   ├── snapshot.py                  # portfolio.snapshot
│   ├── pnl.py                       # portfolio.pnl (read)
│   ├── rebalance.py                 # portfolio.rebalance (write + confirm)
│   └── record_trade.py              # portfolio.record_trade (write + confirm)
├── backtest/
│   └── indicator.py                 # backtest.indicator
└── alert/
    ├── notify.py                    # alert.notify (desktop / webhook)
    └── webhook.py
```

### 10.4 v1 → v2 Tool 映射(充分利用 v1 已有代码)

| v2 Tool | v1 模块 | 备注 |
|---------|--------|------|
| `market.quote` | `CollectionService.get_quote()` | 直接复用 |
| `market.kline` | `CollectionService.get_kline()` | 直接复用 |
| `market.fund_flow` | `CollectionService.get_fund_flow()` | 直接复用 |
| `news.fetch` | `NewsService.collect_news()` | 直接复用 |
| `news.sentiment` | `NewsService.analyze_sentiment()` (DeepSeek) | 复用 + 防御性拦截已就位 |
| `portfolio.positions` | `PortfolioService.get_positions()` | 直接复用 |
| `portfolio.pnl` | `PortfolioService.get_realized_pnl()` | 直接复用 |
| `portfolio.rebalance` | `PortfolioService.suggest_rebalance()` (新) | Phase 1 新增, 调 PyPortfolioOpt |
| `finance.report` | `EvidenceBuilder._build_finance()` | 复用, 包成 Tool |
| `evidence.build` | `EvidenceBuilder.build()` | 复用, 但要避开 Tool 分层(不是"工具") |

### 10.5 Tool 鉴权传递

- **读 Tool**(`required_scopes = ["read"]`): 不需要 API Key, 默认所有 session 有 read 权限
- **写 Tool**(`required_scopes = ["write"]`): 需要 `X-API-Key` 验证 (沿用 v1 模式)
- **确认 Tool**(`required_scopes = ["confirm"]`): 需要用户显式点击确认, `portfolio.rebalance` / `portfolio.record_trade` 属此类
- Orchestrator / UserPreferences 维护 session_scopes, Registry 在 invoke 前比对
- **Tool 内部不直接读 HTTP 头** (单一入口 = Registry)

### 10.6 审计与可观测性

每个 Tool 调用自动记录到 `raw_data` 表(与 v1 一致):

```python
{
    "tool_name": "market.quote",
    "input": {"symbols": ["hk00700"]},
    "output": {"quotes": [...]},
    "duration_ms": 234,
    "trace_id": "task-t5",
    "plan_id": "plan-uuid-1234",
    "source": "orchestrator",
    "data_type": "tool_call",
    "raw_json": "{...}",
    "collected_at": "2026-06-15T16:35:21+08:00"
}
```

**审计要求**:
- 写 Tool (含 `["write"]` 或 `["confirm"]` 权限) **必须** 记录全量 input + output (回溯)
- 读 Tool 可仅记录 input + summary (节省 raw_data 空间)
- 失败的 Tool 调用记录 error_message + stack_trace

### 10.7 Tool 失败处理

| 失败类型 | 处理 |
|---------|------|
| Tool 未注册 | `ToolNotFound` 异常 → Orchestrator 捕获 → Task status="failure" |
| 权限不足 | `InsufficientScope` 异常 → Orchestrator 捕获 → Task status="failure" → Planner 触发重规划(改用其他 Tool) |
| Tool 内部异常 | Tool 抛出, Registry 捕获, 包装为 ToolResult(status="error", error=str(e)) |
| 超时 | Registry 设置 30s 超时 (默认), 超时后取消 Tool 任务, 返回 ToolResult(status="timeout") |
| 输入校验失败 | Pydantic ValidationError → 立即返回, 不进入 Tool.run() |

**关键约束**: Tool 失败**不阻塞 Plan**;Orchestrator 标记该 Task `failure`,其他 Task 继续执行(除非要 depends_on 这个 Task)。

---

## 11. 典型业务流与共享状态机

### 11.1 完整业务流:用户问"新能源板块能不能买"

```
用户输入:"帮我看看今天新能源板块能不能买"
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ State 1: Initialized                                             │
│   Planner 解析意图 → 生成 Task Graph(6 个节点)                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ t1: get_sector_constituents(sector="新能源")             │   │
│   │ t2: get_fund_flow(symbols=<from t1>, days=3)             │   │
│   │ t3: analyze_news_sentiment(symbols=<from t1>, days=7)    │   │
│   │ t4: compute_technical(symbols=<from t1>)                 │   │
│   │ t5: score_buy_signal(fund_flow=<t2>, news=<t3>, tech=<t4>)│  │
│   │ t6: generate_risk_warning(buy_signal=<t5>)               │   │
│   └─────────────────────────────────────────────────────────┘   │
│   写入 shared state: plan_id, tasks, confidence=0.78            │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼  Orchestrator dispatch → t1 ready(无依赖)
   │
┌─────────────────────────────────────────────────────────────────┐
│ State 2: Research_Done                                           │
│   Research Agent 并行执行 t1(t2 / t3 / t4)                      │
│   · 3 阶段流水线过滤(代码 → Map 子线程 → Reduce LLM)           │
│   · 写出"新能源今日简报"(No-Opinion 事实陈述)                  │
│   写入 shared state: evidence_pack, research_report             │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼  Orchestrator dispatch → t5 ready(t2 + t3 + t4 完成)
   │
┌─────────────────────────────────────────────────────────────────┐
│ State 3: Portfolio_Done                                          │
│   Portfolio Agent 调出用户当前持仓                               │
│   · 左脑量化:计算若买入新能源 → 行业集中度从 25% 变 35%       │
│   · 硬代码风控壁垒:35% > 30% 上限 → 强制截断                    │
│   · 右脑 LLM:把数字翻译成"建议最多买 5% 仓位,触发行业上限"   │
│   写入 shared state: buy_signal, rebalance_trades, risk_warning│
└─────────────────────────────────────────────────────────────────┘
   │
   ▼  Orchestrator dispatch → t6 ready(t5 完成)
   │
┌─────────────────────────────────────────────────────────────────┐
│ State 4: Warning_Done                                            │
│   Research Agent t6 生成风控提示                                 │
│   写入 shared state: final_warnings                             │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼  Orchestrator 检查所有节点 → 触发"汇总节点"
   │
┌─────────────────────────────────────────────────────────────────┐
│ State 5: Completed                                               │
│   Planner 汇总节点:把 Research 事实 + Portfolio 建议润色输出    │
│   UI 收到最终结果:                                               │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ ## 新能源板块评估(2026-06-15)                          │   │
│   │ **事实简报**(Research)                                  │   │
│   │ · 成分股 18 只,近 3 日主力净流入 +12.5 亿              │   │
│   │ · 新闻 25 条,正面 14 / 中性 7 / 负面 4                  │   │
│   │ · 技术面:板块指数 MA5 上穿 MA20                         │   │
│   │                                                          │   │
│   │ **调仓建议**(Portfolio)                                  │   │
│   │ · 当前行业集中度 25%,若满仓买入 → 35%(超出上限)        │   │
│   │ · 硬代码风控:建议仓位 ≤ 5%                              │   │
│   │ · 期望收益提升:2.3%(基于 Black-Litterman 模型)          │   │
│   │                                                          │   │
│   │ **风险提示**                                             │   │
│   │ · 行业集中度风险(已截断)                                │   │
│   │ · 财报季临近,业绩不确定性高                              │   │
│   │                                                          │   │
│   │ confidence: 0.72 | evidence_strength: 0.80               │   │
│   │ action: watch | data_used: [4 sources]                   │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 共享状态机(Shared State Machine)

5 个 State 是 Agent 间协作的**共享状态总线**,存储在 Redis / SQLite(Phase 1 用 SQLite 单进程,Phase 2+ 迁 Redis):

| State | 写方 | 读方 | 关键字段 |
|-------|------|------|---------|
| `1. Initialized` | Planner | Orchestrator | `plan_id`, `tasks`, `confidence` |
| `2. Research_Done` | Research Agent | Orchestrator / Portfolio Agent | `evidence_pack`, `research_report` |
| `3. Portfolio_Done` | Portfolio Agent | Orchestrator / Planner(汇总) | `buy_signal`, `rebalance_trades`, `risk_warning` |
| `4. Warning_Done` | Research Agent(t6) | Planner(汇总) | `final_warnings` |
| `5. Completed` | Planner(汇总节点) | UI / Memory | `final_output`, `confidence`, `evidence_strength` |

**状态转换规则**:
- 只允许 `1 → 2 → 3 → 4 → 5` 单向流转
- 任意 State 失败 → 触发 Planner 重规划(回到 State 1)
- Monitoring Agent 触发 → 创建新 Plan_id,新状态机并行运行(不打断当前)

### 11.3 实战踩坑提示(Owner 视角)

> 以下是从多智能体金融系统实战中提炼的关键陷阱。每条都已对应到本文档具体设计点。

#### 坑 1:Research Agent 直接读原始新闻大文本

**现象**: 把 100 条新闻原文 + 50 份财报全文喂给 LLM,Token 消耗炸裂 + 幻觉严重。

**修复**(已在 §5.1 设计):
- **第 1 层:代码硬过滤**(关键词 / 时间 / 来源权威性)→ Top 30 条
- **第 2 层:Map 子线程并行抽取 Fact** → Top 15 Fact dict(每条 ≤ 200 token)
- **第 3 层:Reduce LLM 综合** + 强制 No-Opinion Prompt

#### 坑 2:Portfolio Agent 用 LLM 算数学和仓位

**现象**: LLM 推荐"满仓抄底 + 加 3 倍杠杆",用户照做第二天亏 30%。

**修复**(已在 §5.2 设计 — 双脑架构):
- **左脑(量化)**: PyPortfolioOpt / Markowitz / Black-Litterman / Barra 因子 / VaR
- **右脑(LLM)**: 只翻译数字为人类语言,不做数学
- **硬代码风控壁垒**(LLM 调用前后双重校验):
  - 单行业 ≤ 30% / 单标的 ≤ 20% / 回撤熔断 -15% / 杠杆 ≤ 1.0 / 现金 ≥ 5%
  - LLM 推荐超出 → 截断 + 警告,**不静默**

#### 坑 3:Monitoring Agent 误报率高 → API 账单爆表

**现象**: 每分钟 1000+ 异动全部触发 Alert → 用户被通知轰炸 + 第三方 API 账单天价。

**修复**(已在 §5.3 设计 — 两级过滤):
- **第 1 级:代码硬规则**(零成本)拦截 90% 杂音
- **第 2 级:轻量级小模型**(开源 1B-3B LLM / Embedding 相似度)拦截 8% 情绪噪音
- **第 3 级:核心异动(2%)**才启动 Alert Router → fire_alert + route_to_planner
- **Alert Router 不直接弹窗**,而是通过 `route_to_planner` 发送隐式目标,让 Planner 自动生成应对 Task Graph,合并推送(通知 + 评估)

#### 坑 4:Agent 间两两直接调用 → 死循环

**现象**: Monitoring → Portfolio → Monitoring → Portfolio ... 几秒内死循环。

**修复**(已在 [§7](agents-v2.md#7-event-bus) 设计):
- **强制 Event Bus 解耦**: Agent 间不直接调用,通过 emit_event / subscribe
- **事件总线是单向 fire-and-forget**: 订阅者失败不影响发布者
- **每个 Agent 有自己的状态**: 不假设其他 Agent 的状态,只通过 Event 触发

#### 坑 5:Planner LLM 输出 schema 漂移

**现象**: GPT-4o 输出 `{"task": ...}` 而非 `{"tasks": [...]}`,Orchestrator 解析失败 → 全 Plan 崩溃。

**修复**(已在 [§4.4](agents-v2.md#44-失败处理) 设计):
- **Phase 1 用规则模板**: 不存在 schema 漂移问题(预设结构)
- **Phase 2 引入 LLM 时**: 强绑 Pydantic + `response_format={"type": "json_schema"}`,失败重试 1 次 + fallback
- **schema 校验前置**: Orchestrator 拒绝 dispatch 未通过 Pydantic 校验的 Plan

---


## 附录 B:本设计文档引用的其他文档

- [`docs/v2/architecture-v2.md`](architecture-v2.md) — 6 层架构 + Electron 壳层
- [`docs/architecture-v2.drawio`](../architecture-v2.drawio) — 架构图
- [`docs/v1/architecture.md`](../v1/architecture.md) — v1 架构
- [`docs/v1/dev/lessons_learned.md`](../v1/dev/lessons_learned.md) — 23 条实操经验(继承 v1 写锁 / Evidence / Schema 约束)

## 附录 C:v2 Phase 1 实现优先级

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

## 附录 D:待 Phase 2+ 实现

- Portfolio Agent(依赖更多 v1 投资组合工具)
- Monitoring Agent(持续运行模式)
- Vector Memory(语义检索)
- Strategy Memory 完整演化
- LLM Planner(替换规则模板)
- electron-builder 打包
- Redis pub-sub(多进程支持)

---

> **本文档为 v2 设计稿,代码未启动。** 任何与代码现状冲突时,以代码为准。
