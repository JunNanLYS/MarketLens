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

**工具集**:

| Action | 输入 | 输出 |
|--------|------|------|
| `scan_market_anomaly` | `{tracked_symbols, threshold_pct}` | `{anomalies: [...], collected_at}` |
| `detect_news_burst` | `{raw_news: list, ticker_pool, macro_rules}` | `{layered_results: {layer1_dedup, layer2_scored, layer3_judged}, alerts: [...]}` |
| `detect_fund_flow_anomaly` | `{symbols, threshold_value}` | `{anomalies: [...], source}` |
| `news_simhash_filter` | `{news_list, seen_hashes, threshold=3}` | `{deduped: [...], dropped: [...]}` |
| `news_ticker_linking` | `{news_list, ticker_pool, macro_rules}` | `{linked: [{news, matched_tickers, macro_causal}], unlinked: [...]}` |
| `news_small_model_score` | `{news_list, model="finbert"}` | `{scored: [{news, relevance, polarity, shock_score}]}` |
| `news_llm_judge_batch` | `{news_batch, batch_size=5}` | `{judgments: [{news_id, fundamentally_changed, change_type, ...}]}` |
| `fire_alert` | `{type, severity, payload}` | `{alert_id, dispatched_via: [notify, ui, webhook]}` |
| `route_to_planner` | `{auto_intent, severity, context}` | `{plan_id, dispatched: true}` |
| `register_alert_rule` | `{rule_definition}` | `{rule_id, active: true}` |

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

**兜底方案:因果规则图 + 反向触发**

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
MACRO_KEYWORDS = {
    "战争|冲突|地缘|制裁": ["原油", "黄金", "国防", "美债"],  # 影响行业
    "加息|缩表|通胀": ["科技", "成长股", "银行", "美债"],
    "降息|宽松|QE": ["小盘股", "房地产", "黄金"],
    "出口限制|禁令|封锁": ["粮食", "芯片", "稀土", "对应下游制造业"],
    "汇率|贬值|本币": ["出口企业", "进口依赖型"],
}

def reverse_link(news_text: str, ticker_pool: set[str]) -> set[str]:
    """反向触发:从宏观关键词推断影响的行业/标的。"""
    matched_tickers = set()
    for macro_pattern, affected_sectors in MACRO_KEYWORDS.items():
        if re.search(macro_pattern, news_text):
            for sector in affected_sectors:
                matched_tickers.update(SECTOR_TO_TICKERS.get(sector, []))
    return matched_tickers & ticker_pool
```

**关键约束**:
- 因果规则图必须**人工维护 + 定期 review**(每季度更新)
- 规则命中后,**不直接触发 Alert**,而是给该条新闻打上 `macro_causal=true` 标签,在第 2 层小模型打分时加权(降低 relevance 阈值)
- 用户可关闭某条规则(偏好设置)— 例如"我对黄金不感兴趣"

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

#### 5.4.5 端到端漏斗性能预算

```
每日 10000 条原始新闻
   │
   ├─ 第 1 层 SimHash + Ticker Linking:  10000 → 3000(~0.5s)
   │
   ├─ 第 2 层 FinBERT 小模型:           3000  → 500 (~150s)
   │    (并行 4 进程,实际 ~40s)
   │
   ├─ 第 3 层大模型批量:                500  → 100-200 (~120s)
   │    (batch=5, ~20 次调用)
   │
   └─ 触发 Planner 联动:                100-200 个事件 → 评估后触发 5-15 次 Planner
        │
        ▼
       ~15 个 Alert / 天(用户实际收到)

成本预算:
- SimHash: 0(本地计算)
- FinBERT: 0(本地推理)
- 大模型批量: ~$0.08 / 天
- LLM 触发 Planner: ~$0.05 / 次 × 15 = $0.75 / 天

日总成本: < $1 / 天(可接受)
```

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

## 10. 典型业务流与共享状态机

### 10.1 完整业务流:用户问"新能源板块能不能买"

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

### 10.2 共享状态机(Shared State Machine)

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

### 10.3 实战踩坑提示(Owner 视角)

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

**修复**(已在 [§6](../architecture-v2.md#6-event-bus) 设计):
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
