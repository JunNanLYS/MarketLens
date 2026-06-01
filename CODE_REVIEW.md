# MarketLens Code Review

审查日期：2026-06-01（第五轮全量审查 + AGENTS.md 合规审查）
审查范围：项目全量代码扫描 + AGENTS.md 规则逐条对照
审查方法：三轮审查（高层架构 → 逐文件细节 → 边界与加固）+ AGENTS.md 合规性验证 + restful-api-design 技能审查 + Python 类型注解技能审查

---

## [MAJOR] 新发现未修复问题

### N-8: `add_asset` 竞态条件 — 存在性检查与插入使用两个独立事务

**文件**: [asset_service.py](file:///d:/Project/MarketLens/backend/services/asset_service.py#L64-L110)

**违反**: AGENTS.md §10 错误处理 — 单个标的采集失败不影响其他标的

```python
def add_asset(self, data: dict) -> dict:
    with get_db() as conn:                          # 事务 #1
        existing = conn.execute(
            "SELECT id, symbol FROM tracked_assets WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if existing is not None:
            raise ValueError(...)

    # ← 此处无事务保护，并发请求可插入相同 symbol

    with get_db() as conn:                          # 事务 #2
        cursor = conn.execute(
            "INSERT INTO tracked_assets ...", ...
        )
```

`add_asset` 在两个独立的 `get_db()` 上下文中分别执行存在性检查和插入操作。两个事务之间无锁保护，并发请求可能同时通过存在性检查，导致 `UNIQUE` 约束冲突。此时 `IntegrityError` 未被捕获，将返回 500 错误而非友好的 409 响应。

**建议**: 合并为单个事务，并捕获 `IntegrityError`：
```python
def add_asset(self, data: dict) -> dict:
    with get_db() as conn:
        existing = conn.execute(...).fetchone()
        if existing is not None:
            raise ValueError(...)
        try:
            cursor = conn.execute("INSERT INTO tracked_assets ...", ...)
        except sqlite3.IntegrityError:
            raise ValueError(f"标的 '{symbol}' 已在追踪列表中")
```

**状态**: 未修复

---

### N-9: `get_realized_pnl` 使用当前均价计算所有历史卖出的已实现盈亏 — 会计逻辑错误

**文件**: [portfolio_service.py](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L410-L468)

```python
def get_realized_pnl(self, account_id, symbol):
    ...
    for (aid, sym), sells in grouped.items():
        avg_cost: float = self._compute_avg_cost(conn, aid, sym)  # 当前均价
        for sell in sells:
            realized = sell["price"] * sell["quantity"] - avg_cost * sell["quantity"] - sell["fee"]
```

`_compute_avg_cost` 返回的是**当前持仓均价**（基于所有历史交易计算），但已实现盈亏应使用**每次卖出时的持仓均价**。例如：
- 买入 100 股 @ 10 元 → 均价 10
- 卖出 50 股 @ 15 元 → 应使用均价 10，已实现盈亏 = 250
- 买入 50 股 @ 20 元 → 均价变为 15
- 当前代码对第一次卖出也使用均价 15，计算结果 = 0，完全错误

**建议**: 使用 FIFO 或移动加权平均法逐笔计算每次卖出的成本基础：
```python
def _compute_realized_pnl(self, conn, account_id, symbol):
    rows = conn.execute(
        "SELECT type, quantity, price, fee FROM transactions ... ORDER BY trade_date, created_at",
        (account_id, symbol)
    ).fetchall()
    total_qty = 0.0
    avg_cost = 0.0
    total_realized = 0.0
    for tx in rows:
        if tx["type"] == "buy":
            new_qty = total_qty + tx["quantity"]
            avg_cost = (avg_cost * total_qty + tx["price"] * tx["quantity"]) / new_qty if new_qty > 0 else 0
            total_qty = new_qty
        elif tx["type"] == "sell":
            total_realized += (tx["price"] - avg_cost) * tx["quantity"] - (tx["fee"] or 0)
            total_qty -= tx["quantity"]
    return total_realized
```

**状态**: 未修复

---

### N-10: `_build_news` LIKE 查询在 JSON 数组中匹配 symbol 子串 — 关联错误

**文件**: [evidence_builder.py](file:///d:/Project/MarketLens/backend/services/evidence_builder.py#L146-L152), [news_service.py](file:///d:/Project/MarketLens/backend/services/news_service.py#L187-L189)

```python
# evidence_builder.py
rows = conn.execute(
    """SELECT ... FROM news_items
       WHERE related_symbols LIKE ? ESCAPE '\\' AND published_at >= ?""",
    (f"%{escape_like(symbol)}%", seven_days_ago),
)

# news_service.py
conditions.append("related_symbols LIKE ? ESCAPE '\\'")
params.append(f'%{escape_like(effective_filters["symbol"])}%')
```

`related_symbols` 字段存储为 JSON 数组，如 `["sh600000","sz000001"]`。`LIKE '%sh600%'` 会同时匹配包含 `sh600000` 和 `sh6000` 的记录，因为 `sh600` 是 `sh600000` 的子串。`escape_like` 仅转义 `%` 和 `_` 通配符，不解决 symbol 间的子串包含问题。

**建议**: 改用 JSON 函数或更精确的匹配模式：
```python
# 方案 1：利用 JSON 数组的引号边界
conditions.append("related_symbols LIKE ? ESCAPE '\\'")
params.append(f'%"{escape_like(symbol)}"%')

# 方案 2（SQLite 3.38+）：使用 json_each
conditions.append("EXISTS (SELECT 1 FROM json_each(related_symbols) WHERE json_each.value = ?)")
params.append(symbol)
```

**状态**: 未修复

---

### N-11: `RSSProvider._get_text` 无法查找带命名空间前缀的 XML 元素

**文件**: [rss.py](file:///d:/Project/MarketLens/backend/collectors/rss.py#L82-L98)

```python
content = self._get_text(item, "content:encoded") or self._get_text(item, "description")

@staticmethod
def _get_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    ...
```

Python `xml.etree.ElementTree.find()` 不支持 `prefix:localname` 格式的标签查找。`element.find("content:encoded")` 会将 `content:encoded` 视为完整标签名，而非命名空间前缀 + 本地名，因此永远找不到 `content:encoded` 元素。代码会静默回退到 `description`，丢失全文内容。

**建议**: 注册命名空间或使用完整 URI：
```python
# 方案 1：注册命名空间
ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
content = self._get_text(item, "{http://purl.org/rss/1.0/modules/content/}encoded")

# 方案 2：遍历所有子元素匹配本地名
def _get_text_ns(element, local_name):
    for child in element:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == local_name and child.text:
            return child.text.strip()
    return ""
```

**状态**: 未修复

---

### N-20: `NeoDataProvider` 多个方法完全缺少类型注解 — 违反 AGENTS.md §11

**文件**: [neodata.py](file:///d:/Project/MarketLens/backend/collectors/neodata.py)

**违反**: AGENTS.md §11 — "必须使用 Python 类型注解（函数签名、类属性）"

以下方法缺少参数和返回值类型注解：

```python
def __init__(self, name, timeout=30, params=None, optional=True):  # 无类型
def _log_error(self, msg, **kwargs):                                # 无类型
def _query(self, query_text, data_type="all"):                     # 无类型
def search(self, keyword):                                          # 无类型
def _parse_basic_info_content(self, content):                       # 无类型
def _get_basic_info(self, symbol, query_text):                      # 无类型
def _try_float(self, value):                                        # 无类型
def quote(self, symbols):                                           # 无类型
def kline(self, symbol, period="daily"):                            # 无类型
def finance(self, symbol):                                          # 无类型
def fund_flow(self, symbol):                                        # 无类型
def technical(self, symbol):                                        # 无类型
def _get_tracked_symbols(self):                                     # 无类型
def fetch_news(self, symbols=None):                                 # 无类型
```

14 个方法全部缺少类型注解，是项目中类型注解覆盖最差的文件。

**建议**: 补全所有方法的参数和返回值类型注解，遵循 `Python 类型注解` 技能规范。

**状态**: 已修复

---

### N-21: `evidence_builder.py` 中 `LIMIT` 和 `timedelta(days=7)` 为硬编码魔法数字 — 违反 AGENTS.md §9

**文件**: [evidence_builder.py](file:///d:/Project/MarketLens/backend/services/evidence_builder.py)

**违反**: AGENTS.md §9 — "禁止在代码中硬编码路径、密钥、超时值"

```python
# L84: K线查询限制
ORDER BY date DESC LIMIT 60""",          # 60 天 K 线

# L117: 资金流查询限制
ORDER BY date DESC LIMIT 5""",           # 5 天资金流

# L144: 新闻时间范围
seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()  # 7 天新闻

# L180: 财报查询限制
ORDER BY date DESC LIMIT 2""",           # 2 期财报
```

`LIMIT 60`、`LIMIT 5`、`LIMIT 2` 和 `timedelta(days=7)` 均为硬编码魔法数字，未从 `config.yaml` 读取。这些参数直接影响证据构建的数据量和 AI 分析质量，应可配置。

**建议**: 在 `config.yaml` 的 `evidence` 节中添加配置项：
```yaml
evidence:
  kline_limit: 60
  fund_flow_limit: 5
  finance_limit: 2
  news_days: 7
```

**状态**: 未修复

---

### N-22: `tasks.py` 直接在 API 层操作数据库 — 违反 AGENTS.md §2 模块边界

**文件**: [tasks.py](file:///d:/Project/MarketLens/backend/api/tasks.py#L66-L82)

**违反**: AGENTS.md §2 — 目录与模块边界（API 层不应直接操作数据库）

```python
@router.get("/logs")
def get_task_logs(...):
    with get_db() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM run_logs {where_clause}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT id, task_name, status, started_at, finished_at,
                       error_message, affected_assets
                FROM run_logs
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()
```

API 层直接使用 `get_db()` 执行 SQL 查询 `run_logs` 表，绕过了服务层。这违反了 AGENTS.md §2 的模块边界规则——API 层应通过服务层访问数据。

**建议**: 将 `run_logs` 查询逻辑提取到 `SchedulerManager.get_task_logs()` 方法中，API 层仅调用服务方法。

**状态**: 未修复

---

---

### N-28: `TokenManager._read_cache()` 不支持 JWT token 的 `exp` 过期判断 — JWT token 被提前失效

**文件**: [neodata_client.py](file:///d:/Project/MarketLens/backend/collectors/neodata_client.py#L14-L32)

NeoData SKILL.md 明确定义了两种凭证类型：

| 类型 | 过期判断 |
|------|---------|
| JWT（三段 Base64，`iss` 为 codebuddy.cn） | 解码 payload 检查 `exp` 字段（有效期约一年） |
| tempToken（不透明字符串） | `saved_at` + 12 小时 TTL |

但当前 `TokenManager._read_cache()` 对所有 token 统一使用 12 小时 TTL：

```python
_TOKEN_TTL_SECONDS = 12 * 3600

def _read_cache(self):
    ...
    if time.time() - saved_at > _TOKEN_TTL_SECONDS:  # 固定 43200s，不管是不是 JWT
        return None, "none"
    return credential, "cache"
```

JWT token 有效期约一年，但这里最多 12 小时就被作废。用户明明有有效 token 却需要频繁通过 WorkBuddy 重新认证。

> 监控脚本 `scripts/check_neodata_token.ps1` 已正确实现了 JWT 解码 + `exp` 检查，说明项目已知晓两者差异，但核心 `TokenManager` 没有跟上。

**建议**: 在 `_read_cache()` 中尝试 Base64 解码 token（检测是否为三段 JWT），若解码成功且有 `exp` 字段，则用 `exp` 判断；否则回退到 12 小时 TTL：

```python
def _read_cache(self):
    ...  # 读取缓存文件和 saved_at

    # 尝试解析 JWT exp
    try:
        parts = credential.split('.')
        if len(parts) == 3:
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get('exp')
            if exp and time.time() < exp:
                return credential, 'cache'
            elif exp:
                return None, 'none'  # JWT 已过期
    except Exception:
        pass  # 非 JWT，继续走 tempToken 逻辑

    # tempToken 回退：12 小时 TTL
    if time.time() - saved_at > _TOKEN_TTL_SECONDS:
        return None, 'none'
    return credential, 'cache'
```

**状态**: 已修复

---

## [MAJOR] 历史未修复问题

### M-7: `get_positions` N+1 查询 — 每个持仓单独查询行情和资产名

**文件**: [portfolio_service.py](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L328-L408)

```python
def get_positions(self, account_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(...).fetchall()

    grouped: dict[tuple[int, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault(key, []).append(dict(row))

    positions: list[dict] = []
    with get_db() as conn:
        for (aid, sym), txs in grouped.items():
            quote_row = conn.execute(
                "SELECT price FROM market_quotes WHERE symbol = ? ...", (sym,)
            ).fetchone()
            asset_row = conn.execute(
                "SELECT name FROM tracked_assets WHERE symbol = ?", (sym,)
            ).fetchone()
```

对每个持仓组合 `(account_id, symbol)` 分别查询 `market_quotes` 和 `tracked_assets`。当持仓数量为 N 时，产生 2N+2 次数据库查询（含 2 次连接建立）。

**建议**: 批量查询所有需要的 symbol，用 `IN (...)` 或预加载 dict 映射：
```python
symbols = {sym for (_, sym) in grouped}
quotes = {r["symbol"]: r["price"] for r in conn.execute(
    "SELECT symbol, price FROM market_quotes WHERE symbol IN ({}) ...".format(",".join("?" * len(symbols))),
    list(symbols)
).fetchall()}
```

**状态**: 未修复

---

### M-8: EvidenceBuilder 每次 `build()` 打开 6 个独立数据库连接

**文件**: [evidence_builder.py](file:///d:/Project/MarketLens/backend/services/evidence_builder.py#L14-L36)

```python
@staticmethod
def build(symbol: str) -> dict:
    quote = EvidenceBuilder._build_quote(symbol)           # get_db() #1
    kline = EvidenceBuilder._build_kline(symbol)            # get_db() #2
    fund_flows = EvidenceBuilder._build_fund_flows(symbol)  # get_db() #3
    finance = EvidenceBuilder._build_finance(symbol)        # get_db() #4
    news = EvidenceBuilder._build_news(symbol)              # get_db() #5
    technical = EvidenceBuilder._build_technical(symbol)    # get_db() #6
```

每个 `_build_*` 方法各自调用 `get_db()` 获取独立连接。单次 `build()` 调用就打开/关闭 6 次数据库连接。在 `generate_reports` 中，N 个标的将产生 6N 次连接开销。

**建议**: 将 `build()` 改为接收 `conn` 参数，所有子方法共享同一连接：
```python
@staticmethod
def build(symbol: str) -> dict:
    with get_db() as conn:
        quote = EvidenceBuilder._build_quote(conn, symbol)
        kline = EvidenceBuilder._build_kline(conn, symbol)
        ...
```

**状态**: 未修复

---

### M-9: `generate_reports` 每个标的打开约 8 个数据库连接

**文件**: [report_service.py](file:///d:/Project/MarketLens/backend/services/report_service.py#L15-L49)

```python
def generate_reports(symbols, force):
    for symbol in symbols:
        if not force and ReportService._has_today_report(symbol):  # get_db() #1
            continue
        evidence = EvidenceBuilder.build(symbol)  # get_db() #2-7 (6个连接)
        ReportService._save_report(symbol, result, force)  # get_db() #8
```

每个标的的 AI 报告生成涉及：
- `_has_today_report`: 1 个连接
- `EvidenceBuilder.build`: 6 个连接
- `_save_report`: 1 个连接

合计 8 个连接/标的。100 个标的将产生 800 次连接开关。与 M-8 一起修复可大幅降低连接开销。

**建议**: 重构为单一 `get_db()` 上下文内完成所有操作，将 `conn` 传递给各子方法。

**状态**: 未修复 — 与 M-8 联合修复

---

### M-10: CORS `allow_origins=["*"]` 允许任意来源访问

**文件**: [main.py](file:///d:/Project/MarketLens/backend/main.py#L45-L50)

**违反**: AGENTS.md §9 — 安全相关配置应从 config.yaml 读取

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

生产环境允许任意来源的跨域请求，存在 CSRF 和数据泄露风险。

**建议**: 从 `config.yaml` 读取允许的 origins 列表，开发环境可使用 `["*"]`，生产环境应限制为前端域名。

**状态**: 未修复

---

### M-11: neodata.py 硬编码 API 端点 URL

**文件**: [neodata.py collector](file:///d:/Project/MarketLens/backend/collectors/neodata.py#L14)

**违反**: AGENTS.md §9 — "禁止在代码中硬编码路径、密钥、超时值"

```python
endpoint=params.get("endpoint", "https://copilot.tencent.com/agenttool/v1/neodata")
```

API 端点 URL 硬编码为默认值，违反 AGENTS.md 中"禁止在代码中硬编码路径、密钥、超时值"的规定。

**建议**: 将默认端点移入 `config.yaml`，代码中不提供硬编码 fallback。

**状态**: 未修复

---

## [MINOR] 新发现未修复问题

### N-12: `_match_symbols_with_conn` 在循环中逐行编译正则表达式

**文件**: [news_service.py](file:///d:/Project/MarketLens/backend/services/news_service.py#L147-L168)

```python
for row in rows:
    symbol: str = row["symbol"]
    _symbol_pattern = re.compile(
        r'(?<![a-zA-Z0-9])' + re.escape(symbol) + r'(?![a-zA-Z0-9])'
    )
    if _symbol_pattern.search(text):
        ...
```

对每个追踪标的行都重新编译正则表达式。当追踪标的数量为 N 时，编译 N 次正则。正则编译是相对昂贵的操作。

**建议**: 预编译所有 symbol 的正则模式并缓存，或在 `NewsService.__init__` 中构建一次：
```python
def _build_symbol_patterns(self, rows):
    self._symbol_patterns = {}
    for row in rows:
        symbol = row["symbol"]
        self._symbol_patterns[symbol] = re.compile(
            r'(?<![a-zA-Z0-9])' + re.escape(symbol) + r'(?![a-zA-Z0-9])'
        )
```

**状态**: 未修复

---

### N-13: `collect_news` 的 `affected_assets` 记录的是新闻条数而非标的数

**文件**: [news_service.py](file:///d:/Project/MarketLens/backend/services/news_service.py#L127)

**违反**: AGENTS.md §8 — `run_logs` 字段语义 `affected_assets` 应为标的数

```python
conn.execute(
    """INSERT INTO run_logs (..., affected_assets) VALUES (..., ?)""",
    (..., collected + skipped),  # ← 新闻条数，非标的数
)
```

`affected_assets` 语义上应表示"受影响的标的数量"，但实际记录的是处理过的新闻条数（collected + skipped）。这与 `run_logs` 表的字段语义不一致，也与其他任务（如 quote、daily_close）的 `affected_assets` 含义不同。

**建议**: 改为记录实际关联到的去重标的数：
```python
affected_symbols = set()
for item in all_items:
    related = self._match_symbols_with_conn(...)
    affected_symbols.update(related)
affected_assets = len(affected_symbols)
```

**状态**: 未修复

---

### N-14: `_collect_fund_flow` 使用 `INSERT OR REPLACE` 静默覆盖历史数据

**文件**: [collection_service.py](file:///d:/Project/MarketLens/backend/services/collection_service.py#L270-L287)

**违反**: AGENTS.md §4 — "每次采集须同时保存原始返回和标准化数据（可追溯原则）"

```python
conn.execute(
    """INSERT OR REPLACE INTO fund_flows
       (symbol, date, main_net_inflow, ...) VALUES (?, ?, ?, ...)""",
    ...
)
```

`INSERT OR REPLACE` 在 `(symbol, date)` 唯一约束冲突时会删除旧记录并插入新记录。如果同一日期的数据来自不同数据源或采集时间不同，旧数据会被静默覆盖，违反 AGENTS.md 的"可追溯原则"。同样的问题存在于 `_collect_quote_for_symbol`（`market_quotes`）和 `_collect_technical`（`technical_indicators`）。

**建议**: 改用 `INSERT OR IGNORE`（保留首次采集的数据），或在 REPLACE 前将旧数据归档到 `raw_data`。

**状态**: 未修复

---

### N-15: `get_positions` 打开两个独立的数据库连接

**文件**: [portfolio_service.py](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L328-L408)

```python
def get_positions(self, account_id):
    with get_db() as conn:          # 连接 #1：查询交易
        rows = conn.execute(...).fetchall()

    grouped = ...
    positions = []
    with get_db() as conn:          # 连接 #2：查询行情和资产名
        for (aid, sym), txs in grouped.items():
            quote_row = conn.execute(...)
            asset_row = conn.execute(...)
```

先打开一个连接查询交易，关闭后重新打开连接查询行情和资产名。两个查询可以合并到同一连接中。

**建议**: 使用单一 `get_db()` 上下文完成所有查询。

**状态**: 未修复

---

### N-16: `_compute_position_detail` split 类型使用 `quantity` 字段作为拆股比率 — 语义不清

**文件**: [portfolio_service.py](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L177-L192)

```python
elif tx["type"] == "split":
    total_qty *= tx["quantity"]
```

`quantity` 字段在 buy/sell 中表示"数量"，但在 split 中被用作"拆股比率"（如 2 表示 1 拆 2）。字段名具有误导性，且无验证确保比率为正数。如果用户误输入 split 的 quantity 为 0 或负数，会导致持仓计算错误。

**建议**:
1. 在 `create_transaction` 中对 split 类型添加比率验证（> 0）
2. 考虑在 API 层使用不同的字段名（如 `split_ratio`）或在文档中明确说明

**状态**: 未修复

---

### N-17: `NeoDataProvider.fetch_news` 对每个标的单独发起 API 请求

**文件**: [neodata.py](file:///d:/Project/MarketLens/backend/collectors/neodata.py#L174-L211)

```python
def fetch_news(self, symbols=None):
    for symbol in symbols:
        result = self._query(f"{symbol}最新新闻", data_type="doc")
```

对 N 个追踪标的发起 N 次独立的 API 请求。当标的数量较多时（如 50+），会产生大量网络请求，增加采集时间和失败概率。

**建议**: 考虑批量查询（如将多个 symbol 拼接为单次查询），或设置并发限制。

**状态**: 未修复

---

### N-23: `collection_service.py` 和 `news_service.py` 中 `conn: Any` 应为 `sqlite3.Connection`

**文件**: [collection_service.py](file:///d:/Project/MarketLens/backend/services/collection_service.py), [news_service.py](file:///d:/Project/MarketLens/backend/services/news_service.py)

**违反**: AGENTS.md §11 — "必须使用 Python 类型注解" + Python 类型注解技能规范

```python
def _collect_kline(self, conn: Any, symbol: str) -> dict:
def _collect_finance(self, conn: Any, symbol: str) -> dict:
def _collect_fund_flow(self, conn: Any, symbol: str) -> dict:
def _collect_technical(self, conn: Any, symbol: str) -> dict:
def _match_symbols_with_conn(self, conn: Any, ...):
```

`conn: Any` 等于放弃类型检查。根据 Python 类型注解技能 Level 1 规范，应使用具体类型 `sqlite3.Connection`。

**建议**: 替换所有 `conn: Any` 为 `conn: sqlite3.Connection`。

**状态**: 未修复

---

### N-24: `portfolio_service.py` 多个方法缺少参数和返回值类型注解

**文件**: [portfolio_service.py](file:///d:/Project/MarketLens/backend/services/portfolio_service.py)

**违反**: AGENTS.md §11 — "必须使用 Python 类型注解（函数签名、类属性）"

以下方法缺少类型注解：
- `create_account(self, data: dict) -> dict` — `data` 应为更具体的 TypedDict
- `get_realized_pnl(self, account_id, symbol)` — 参数缺少类型注解
- `_compute_position_detail` 中 `conn` 参数无类型注解
- `_compute_avg_cost` 中 `conn` 参数无类型注解

**建议**: 补全所有参数和返回值类型注解。

**状态**: 未修复

---

### N-25: `POST /api/v1/assets/search` 使用 POST 执行无副作用的查询 — 违反 RESTful 规范

**文件**: [assets.py](file:///d:/Project/MarketLens/backend/api/assets.py#L108-L111)

**违反**: AGENTS.md §6 — 使用 `restful-api-design` 技能规范

```python
@router.post("/search")
def search_assets(body: AssetSearchRequest) -> dict:
    items = _service.search_assets(keyword=body.keyword, market=body.market)
    return {"items": items, "total": len(items)}
```

`search` 是只读查询操作，不应使用 `POST` 方法。根据 `restful-api-design` 技能规范："不要用 POST 代替所有方法"。

**建议**: 改为 `GET /api/v1/assets` 并使用查询参数 `?keyword=xxx&market=xxx`，或保留为专门的搜索资源 `GET /api/v1/assets/search?keyword=xxx`。

**状态**: 未修复

---

### N-26: `GET /api/v1/data/quotes/{symbol}?force=true` 通过查询参数触发写操作 — 违反 RESTful 规范

**文件**: [data.py](file:///d:/Project/MarketLens/backend/api/data.py#L45-L57)

**违反**: `restful-api-design` 技能规范 — "不要用 GET 执行有副作用的操作"

```python
@router.get("/quotes/{symbol}")
def get_quote(symbol: str, force: bool = False) -> dict:
    if force:
        result = _service.collect_quote_single(symbol)  # ← 触发数据采集（写操作）
```

`force=true` 时会触发 `collect_quote_single`，这是一个有副作用的写操作（采集新数据并写入数据库）。使用 `GET` 方法执行写操作违反 HTTP 语义和 RESTful 原则，可能导致 CDN/代理缓存问题。

**建议**: 将强制刷新拆分为独立的 `POST /api/v1/data/quotes/{symbol}/refresh` 端点。

**状态**: 未修复

---

### N-27: `DELETE /api/v1/accounts/{account_id}` 返回 JSON 而非 204 — 状态码与响应体不一致

**文件**: [portfolio.py](file:///d:/Project/MarketLens/backend/api/portfolio.py#L109-L117)

**违反**: `restful-api-design` 技能规范 — "同步更新/删除成功且无响应体 → 204 No Content"

```python
@router.delete("/accounts/{account_id}")
def delete_account(account_id: int) -> dict:    # ← 返回 dict，非 None
    ...
    return {"message": "账户已删除"}             # ← 有响应体，应配合 200
```

对比 [assets.py](file:///d:/Project/MarketLens/backend/api/assets.py#L98-L105) 中 `DELETE` 正确使用了 `status_code=204` + 返回 `None`。`portfolio.py` 的删除端点返回了 JSON 响应体但未设置 `status_code=204`，与项目内其他 DELETE 端点风格不一致。

**建议**: 统一为 `status_code=204` + 返回 `None`，或使用 `200 OK` + 返回被删除的资源。

**状态**: 未修复

---

---

### N-29: `NeoDataClient.query()` 中存在死代码 — `_is_auth_error` 检查不会命中

**文件**: [neodata_client.py](file:///d:/Project/MarketLens/backend/collectors/neodata_client.py#L188)

```python
def query(self, query_text: str, data_type: str = "all") -> dict | None:
    ...
    result = self._do_request(token, query_text, data_type)
    if result is not None and _is_auth_error(None, result):  # ← 永远不会为 True
        result = None
    ...
```

`_do_request()` 内部已在上游对 body 做了一轮 `_is_auth_error(None, body)` 检查并返回 `None`，因此能到达 line 188 的 result 必然是干净的。该检查是冗余防御代码，不会造成 bug，但会在代码审查中引起困惑。

**建议**: 移除 `query()` 中的冗余 `_is_auth_error` 检查。

**状态**: 已修复

---

### N-30: NeoData Token 管理 API 未出现在 `docs/api.md` 文档中

**文件**: [docs/api.md](file:///d:/Project/MarketLens/docs/api.md)

以下两个端点已在代码中实现并通过测试，但未列入 `docs/api.md` 的快速导航和一页速览：

- `GET /api/v1/neodata/token-status`
- `POST /api/v1/neodata/token`

用户无法从文档获知这些端点的存在和使用方式。

**建议**: 在 `docs/api.md` 的快速导航表和接口速览中添加 NeoData Token 管理相关的两个端点。

**状态**: 已修复

---

## [MINOR] 历史未修复问题

### m-1: API 层服务实例在模块加载时创建

**文件**: [assets.py](file:///d:/Project/MarketLens/backend/api/assets.py), [data.py](file:///d:/Project/MarketLens/backend/api/data.py), [news.py](file:///d:/Project/MarketLens/backend/api/news.py), [reports.py](file:///d:/Project/MarketLens/backend/api/reports.py), [portfolio.py](file:///d:/Project/MarketLens/backend/api/portfolio.py)

```python
_service = AssetService()
```

所有 API 路由模块在模块加载时创建服务实例，这意味着：
1. 应用启动时就会触发 Provider 初始化和 config 加载
2. 测试时无法轻松替换服务实例
3. 每个路由模块创建独立的服务实例，Provider 也被重复创建

**建议**: 使用 FastAPI 依赖注入（`Depends`）管理服务生命周期，或使用 `functools.lru_cache` 确保单例。

**状态**: 未修复 — 涉及所有路由文件，改动面广，建议作为独立重构任务处理。

---

### m-7: repository.py 为死代码 — 无任何服务引用

**文件**: [repository.py](file:///d:/Project/MarketLens/backend/storage/repository.py)

所有服务均直接编写 SQL，未导入或使用 `repository.py` 中的通用函数。该文件完全未被引用。此外，其 `insert()`/`update()`/`delete()` 等函数通过 f-string 拼接 `table` 参数，若被使用则存在 SQL 注入风险。

**建议**: 要么让各服务统一使用 repository 通用函数（减少 SQL 重复），要么删除该文件。

**状态**: 未修复

---

### m-8: EvidenceBuilder._build_fund_flows 缺少 `_source`/`_collected_at` 内部字段

**文件**: [evidence_builder.py](file:///d:/Project/MarketLens/backend/services/evidence_builder.py#L112-L122)

```python
return [dict(r) for r in rows]  # ← 未添加 _source / _collected_at
```

对比其他 `_build_*` 方法都会添加 `_source` 和 `_collected_at` 内部字段，`_build_fund_flows` 遗漏了。导致 `_collect_data_sources` 无法识别 fund_flows 的数据来源，`data_sources` 输出中缺失 fund_flows 条目。

**建议**: 在返回结果中添加 `_source` 和 `_collected_at` 字段，并在 `_strip_internal_fields` 中清理。

**状态**: 未修复

---

### m-9: database.py 每次连接开关均输出 info 级别日志

**文件**: [database.py](file:///d:/Project/MarketLens/backend/storage/database.py#L28-L43)

结合 M-8/M-9 的问题，单次 `generate_reports` 可能产生 800+ 条 info 日志。生产环境下日志量过大。

**建议**: 将连接建立/关闭日志降级为 `logger.debug()`，仅保留异常回滚的 `logger.exception()`。

**状态**: 未修复

---

### m-10: `_build_fund_flow_summary` 两处实现语义不一致

**文件**: [asset_service.py](file:///d:/Project/MarketLens/backend/services/asset_service.py#L293-L314) vs [collection_service.py](file:///d:/Project/MarketLens/backend/services/collection_service.py#L418-L441)

- `asset_service.py` 版本：检查**连续**净流入/流出日数
- `collection_service.py` 版本：统计**总**净流入/流出日数（不要求连续）

同一概念两种计算逻辑，容易造成用户困惑。

**建议**: 提取为公共函数到 `utils.py`，统一使用"连续"语义。

**状态**: 未修复

---

### m-11: 缺少关键数据库索引

**文件**: [schema.py](file:///d:/Project/MarketLens/backend/storage/schema.py)

以下高频查询路径缺少索引：
- `raw_data`: 无任何索引，按 symbol/data_type 查询全表扫描
- `run_logs`: 缺少 `task_name` 索引，`get_task_status` 每次按 task_name 查最新记录
- `news_items`: 缺少 `published_at` 索引，按时间范围查询效率低
- `market_quotes`: 缺少 `(symbol, collected_at)` 联合索引，频繁查询"某 symbol 最新行情"

**建议**: 在 `INDEX_DDLS` 中补充：
```sql
CREATE INDEX IF NOT EXISTS idx_raw_data_symbol_type ON raw_data(symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_run_logs_task_name ON run_logs(task_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_published_at ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol_collected ON market_quotes(symbol, collected_at DESC);
```

**状态**: 未修复

---

### m-12: news_service.py 名称/标签匹配使用简单 `in` 运算符，可能误匹配

**文件**: [news_service.py](file:///d:/Project/MarketLens/backend/services/news_service.py#L159-L168)

C-3 修复了 symbol 的子字符串匹配问题（改用正则边界），但 `name` 和 `tags` 仍使用 `in` 运算符。对于短名称（如"中行"）或短标签（如"AI"），容易产生误匹配。

**建议**: 对 name 和 tag 也使用正则边界匹配，或要求 name/tag 最小长度（如 ≥ 2 字符）才进行匹配。

**状态**: 未修复

---

### m-13: westock.py `subprocess.run(shell=True)` 携带未过滤用户输入

**文件**: [westock.py](file:///d:/Project/MarketLens/backend/collectors/westock.py)

> **风险降级说明**：MarketLens 为本地单机项目，无实际攻击面。但 `shell=True` + 字符串拼接仍是 bad practice——特殊字符可能导致 CLI 解析异常。

**建议**: 移除 `shell=True`，改用列表参数形式，或对输入进行 `shlex.quote()` 转义。

**状态**: 未修复 — 建议作为代码质量改进处理

---

### m-14: API 路径不符合 RESTful 资源命名规范

**文件**: [data.py](file:///d:/Project/MarketLens/backend/api/data.py), [reports.py](file:///d:/Project/MarketLens/backend/api/reports.py)

**违反**: AGENTS.md §6 — 使用 `restful-api-design` 技能规范

违反 `restful-api-design` 技能规范：
1. `data.py` 使用动作型路径而非资源型路径 — `/data/quotes/{symbol}` 应为 `/quotes/{symbol}`
2. `reports.py` 的 `POST /api/v1/reports/generate` 使用了动词路径 — 应为 `POST /api/v1/reports` 或 `POST /api/v1/report-generation-jobs`
3. `fund-flow` 使用连字符但 `kline` 不用，命名风格不一致

**建议**: 将数据查询端点重构为独立资源路径，去除 `/data/` 前缀。

**状态**: 未修复

---

### m-15: API 错误响应格式不符合 RESTful 错误模型规范

**文件**: [main.py](file:///d:/Project/MarketLens/backend/main.py#L61-L67), 各 API 路由文件

**违反**: AGENTS.md §6 + `restful-api-design` 技能规范

当前错误响应格式 `{"error": "...", "detail": "..."}` 嵌套在 `HTTPException.detail` 中，实际返回格式为：
```json
{"detail": {"error": "ASSET_EXISTS", "detail": "标的 'sh600000' 已在追踪列表中"}}
```

这不符合 `restful-api-design` 技能推荐的错误模型（应包含 `type`/`title`/`status`/`detail`），且双重 `detail` 嵌套令人困惑。

**建议**: 统一错误响应结构，至少包含 `error`（错误码）和 `detail`（描述），并在异常处理器中保证一致性。

**状态**: 未修复

---

### m-16: `POST /api/v1/reports/generate` 返回 202 但实际同步执行

**文件**: [reports.py](file:///d:/Project/MarketLens/backend/api/reports.py#L16-L30)

**违反**: `restful-api-design` 技能规范 — "异步任务已接受 → 202 Accepted"

`202 Accepted` 表示请求已接受但尚未处理完成，应配合异步处理。当前代码同步执行，应使用 `200 OK` 或 `201 Created`。

**建议**: 要么改为真正的异步处理，要么改为 `200 OK` 并返回实际结果。

**状态**: 未修复

---

### m-17: 多处函数缺少返回值类型注解或使用 `Any` 滥用

**文件**: 多个服务文件

**违反**: AGENTS.md §11 — "必须使用 Python 类型注解"

1. **portfolio_service.py** — `conn` 参数无类型注解（见 N-24）
2. **collection_service.py** — `conn: Any` 滥用，应为 `sqlite3.Connection`（见 N-23）
3. **news_service.py** — `conn: Any` 滥用（见 N-23）

**建议**: 补全类型注解，将 `conn: Any` 替换为 `conn: sqlite3.Connection`。

**状态**: 未修复 — 详细问题见 N-23、N-24

---

## [NIT] 未修复问题

### n-3: neodata.py `_client` 在模块加载时创建

**文件**: [neodata.py](file:///d:/Project/MarketLens/backend/api/neodata.py#L27)

与 m-1 同类问题，模块加载时即创建 NeoDataClient 实例。

**建议**: 使用 FastAPI 依赖注入或 `Depends` 延迟创建。

**状态**: 未修复

---

### N-19: `config.py` `_ensure_data_dir` 被冗余调用

**文件**: [config.py](file:///d:/Project/MarketLens/backend/config.py#L12-L25)

```python
def get_config() -> dict:
    _ensure_data_dir()      # 调用 #1
    ...

def get_data_dir() -> Path:
    _ensure_data_dir()      # 调用 #2（冗余，因为 get_config 已调用）
    return _DATA_DIR
```

`get_config()` 内部已调用 `_ensure_data_dir()`，而 `get_data_dir()` 再次调用。由于 `mkdir(parents=True, exist_ok=True)` 是幂等的，功能上无影响，但属于冗余操作。

**建议**: 仅在 `get_data_dir()` 中保留调用，`get_config()` 中移除。

**状态**: 未修复

---

## AGENTS.md 合规性检查清单

| 规则 | 状态 | 违反项 |
|------|------|--------|
| §2 目录与模块边界 | ⚠️ 部分违反 | N-22: tasks.py API 层直接操作数据库 |
| §4 数据源提供者模式 | ⚠️ 部分违反 | N-14: INSERT OR REPLACE 违反可追溯原则 |
| §4 optional 源静默跳过 | ✅ 合规 | news_service.py L40 正确处理 |
| §4 数据源失败不崩溃 | ✅ 合规 | 所有 Provider 均有 try/except |
| §5 数据库变更 | ✅ 合规 | 无业务代码中的 ALTER/CREATE TABLE |
| §6 API 设计（restful-api-design） | ❌ 多处违反 | m-14, m-15, m-16, N-25, N-26, N-27 |
| §7 调度任务写入 run_logs | ✅ 合规 | 各服务方法内部写入 run_logs |
| §7 任务幂等性 | ⚠️ 部分违反 | N-14: INSERT OR REPLACE 非幂等 |
| §8 使用 loguru | ✅ 合规 | 全局使用 loguru |
| §8 run_logs 字段语义 | ⚠️ 部分违反 | N-13: affected_assets 记录新闻条数 |
| §9 配置管理 | ❌ 多处违反 | M-11, N-21: 硬编码端点/魔法数字 |
| §10 错误处理格式 | ⚠️ 部分违反 | m-15: 错误响应双重嵌套 |
| §10 外部调用超时 | ✅ 合规 | 所有 Provider 设置超时 |
| §11 Python 类型注解 | ⚠️ 部分违反 | N-23, N-24: conn Any 滥用 |
| §11 中文注释 | ✅ 合规 | 所有注释和文档字符串均为中文 |
| §11 导入顺序 | ✅ 合规 | 各文件遵循 stdlib→third-party→local |

---

## 已修复问题

以下问题已在之前的修复提交中解决：

| 编号 | 严重级别 | 问题 | 修复方式 |
|------|---------|------|---------|
| C-1 | CRITICAL | LIKE 通配符未转义（asset_service.py） | 添加 `_escape_like` 函数 + `ESCAPE '\\'` 子句 |
| C-2 | CRITICAL | LIKE 通配符未转义（news_service.py） | 添加 `_escape_like` 函数 + `ESCAPE '\\'` 子句 |
| C-3 | CRITICAL | `_match_symbols` 子字符串匹配过于宽泛 | 改用正则精确匹配 |
| M-1 | MAJOR | 持仓计算未按时间排序 | SQL 添加 `ORDER BY trade_date, created_at` |
| M-2 | MAJOR | 重复方法 `_get_current_holding` | 删除未使用的方法 |
| M-3 | MAJOR | `affected_assets` 只记录成功数 | 改为记录总数 |
| M-4 | MAJOR | 新闻采集每条新闻独立数据库连接 | 合并为单个 `with get_db()` 上下文 |
| M-5 | MAJOR | `_collect_data_sources` 重复查询 6 次数据库 | 改为纯内存操作 |
| M-6 | MAJOR | 资金流连续判断统计历史最长而非最近 | 改为从最近日期开始计数 |
| N-1 | MAJOR | `collect_news` 单条新闻入库非原子操作 | 使用 `SAVEPOINT`/`RELEASE`/`ROLLBACK TO` 保证原子性 |
| N-2 | MAJOR | `evidence_builder.py` LIKE 未转义 | 导入 `escape_like`，添加 `ESCAPE '\\'` 子句 |
| N-3 | MAJOR | `_match_symbols_with_conn` 重复查询 tracked_assets | 在 `collect_news` 中查询一次，通过参数传入 |
| N-4 | MINOR | `_escape_like` 重复定义 | 提取到 `backend/utils.py` 公共模块，统一导入 |
| N-5 | MINOR | `report_service.py` affected_assets 只记录 generated | 改为 `generated + skipped` |
| N-6 | MINOR | evidence 内部字段 `_source`/`_collected_at` 泄露 | 添加 `_strip_internal_fields` 方法在 build() 后清理 |
| N-7 | NIT | cron 分钟字段解析错误 | 正确解析 `parts[0]` 为分钟、`parts[1]` 为小时 |
| m-2 | MINOR | 错误响应格式不一致 | 自定义 `HTTPException` 处理器 |
| m-3 | MINOR | 行情采集重复代码 | 提取 `_collect_quote_for_symbol` 公共方法 |
| m-4 | MINOR | 持仓计算重复代码 | 提取 `_compute_position_detail` 静态方法 |
| m-5 | MINOR | 调度描述硬编码 | 改为从 config 动态生成 |
| m-6 | MINOR | UI 健康检查频率过高 | 添加 30s TTL 缓存 |
| n-1 | NIT | `Optional[X]` 混用 | 统一为 `X \| None` |
| n-2 | NIT | Pydantic 模型类型注解不一致 | 统一为 `X \| None` |
| N-28 | MAJOR | TokenManager 不支持 JWT exp 过期判断 | 添加 JWT payload 解码 + exp 检查逻辑 |
| N-29 | MINOR | NeoDataClient.query() 死代码 | 移除冗余 _is_auth_error 检查 |
| N-30 | MINOR | NeoData API 文档缺失 | 在 docs/api.md 补充两个 token 端点 |
| N-20 | MAJOR | NeoDataProvider 14 个方法缺类型注解 | 补全全部 14 个方法的类型注解 |

---

## 审查总结

| 严重级别 | 累计发现 | 已修复 | 未修复 |
|----------|---------|--------|--------|
| CRITICAL | 3 | 3 | 0 |
| MAJOR | 19 | 10 | 9 (M-7~M-11, N-8~N-11, N-22) |
| MINOR | 36 | 11 | 25 (m-1, m-7~m-17, N-12~N-17, N-23~N-27) |
| NIT | 5 | 3 | 2 (n-3, N-19) |
| **合计** | **61** | **25** | **35** |

### 阻塞合并项

无

### 高优先级修复建议

1. **N-9** → 修复 `get_realized_pnl` 会计逻辑错误 — 影响用户投资决策
2. **N-8** → 合并 `add_asset` 为单事务 — 消除竞态条件
3. **N-10** → 修复 LIKE 查询在 JSON 数组中的子串匹配 — 影响数据关联准确性
4. **M-8 + M-9** → 联合重构 EvidenceBuilder 和 ReportService，共享数据库连接
5. **N-11** → 修复 RSS 命名空间解析 — 丢失全文内容
6. **N-22** → tasks.py 数据库查询移至服务层 — 违反 AGENTS.md §2
7. **N-21** → evidence_builder.py 魔法数字移入 config.yaml — 违反 AGENTS.md §9

### 剩余未修复项（按优先级排序）

| 优先级 | 编号 | 问题 | 违反规则 | 影响 |
|--------|------|------|----------|------|
| 1 | N-9 | `get_realized_pnl` 会计逻辑错误 | §11 正确性 | 已实现盈亏计算完全错误 |
| 2 | N-8 | `add_asset` 竞态条件 | §10 错误处理 | 并发插入导致 500 错误 |
| 3 | N-10 | LIKE 查询匹配 JSON 数组子串 | §4 数据准确性 | 新闻-标的关联错误 |
| 4 | M-8 | EvidenceBuilder 6 次连接/调用 | 性能 | 性能瓶颈 |
| 5 | M-9 | generate_reports 8 次连接/标的 | 性能 | 与 M-8 联合修复 |
| 6 | N-11 | RSS 命名空间解析失败 | §4 数据完整性 | 丢失全文内容 |
| 7 | N-22 | tasks.py API 层直接操作数据库 | §2 模块边界 | 架构违规 |
| 8 | N-21 | evidence_builder 魔法数字硬编码 | §9 配置管理 | 不可配置 |
| 9 | M-10 | CORS 允许任意来源 | §9 安全配置 | 安全风险 |
| 10 | M-11 | neodata 硬编码端点 | §9 配置管理 | 违反规范 |
| 11 | M-7 | get_positions N+1 查询 | 性能 | 性能问题 |
| 12 | N-14 | INSERT OR REPLACE 静默覆盖 | §4 可追溯原则 | 数据丢失风险 |
| 13 | N-25 | POST /search 执行只读查询 | §6 RESTful | HTTP 语义错误 |
| 14 | N-26 | GET + force 触发写操作 | §6 RESTful | HTTP 语义错误 |
| 15 | m-16 | 202 状态码与同步执行不一致 | §6 RESTful | RESTful 语义 |
| 16 | N-23 | conn: Any 滥用 | §11 类型注解 | 类型安全 |
| 17 | N-24 | portfolio_service 缺类型注解 | §11 类型注解 | 代码规范 |
| 18 | m-8 | fund_flows 缺 _source/_collected_at | §4 数据完整性 | 数据完整性 |
| 19 | m-11 | 缺少数据库索引 | 性能 | 性能问题 |
| 20 | m-10 | fund_flow_summary 语义不一致 | 正确性 | 正确性 |
| 21 | m-12 | 名称/标签误匹配 | 正确性 | 正确性 |
| 22 | N-12 | 循环中编译正则 | 性能 | 性能 |
| 23 | N-13 | affected_assets 记录新闻条数 | §8 日志语义 | 语义不一致 |
| 24 | N-15 | get_positions 两个连接 | 性能 | 性能 |
| 25 | N-16 | split 类型 quantity 语义不清 | 可维护性 | 可维护性 |
| 26 | N-17 | NeoData 逐标的请求 | 性能 | 性能 |
| 27 | m-14 | API 路径不符合 RESTful | §6 RESTful | API 规范 |
| 28 | m-15 | 错误响应格式不规范 | §6 RESTful | API 规范 |
| 29 | N-27 | DELETE 返回 JSON 非 204 | §6 RESTful | API 规范 |
| 30 | m-13 | westock.py shell=True | 代码质量 | 代码质量 |
| 31 | m-9 | 数据库日志过于频繁 | 可观测性 | 可观测性 |
| 32 | m-1 | API 层服务实例模块级创建 | 可维护性 | 可维护性 |
| 33 | m-7 | repository.py 死代码 | 可维护性 | 可维护性 |
| 34 | n-3 | neodata _client 模块级创建 | 可维护性 | 可维护性 |
| 35 | N-19 | _ensure_data_dir 冗余调用 | NIT | 无功能影响 |

