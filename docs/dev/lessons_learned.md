# MarketLens 经验速查表（Lessons Learned）

> **新会话接手 5 分钟扫读版**。所有"踩过的坑"与"实操最佳实践"集中归档，
> 避免分散在 CLAUDE.md / ISSUES.md / 归档文件各处反复探索。
>
> **维护规则**：发现新经验 → 追加到本文件相应章节。修复归档（`docs/dev/issues_*.md`）
> 保留完整决策历史,但速查表只保留"可复用的最佳实践"。

---

## 0. 速查清单（5 分钟版）

| # | 主题 | 关键一句话 | 严重度 |
|---|------|-----------|--------|
| 1 | 写锁 | **所有 SQLite 写路径必须 `with _WRITE_LOCK:`** | 🔴 P0 |
| 2 | UI 分层 | **`ui/` 严禁 import `backend/storage/`** | 🔴 P0 |
| 3 | 文档同步 | **改后端必动 `docs/api/*.md`** | 🟡 P1 |
| 4 | evidence 审计 | **AI 输出必须含 `data_used` 字段** | 🟡 P1 |
| 5 | Provider 关闭 | **`_HttpClientMixin` 已是叶子节点，base 不要再 `super().close()`** | 🔴 CRITICAL |
| 6 | 锁测试 | **`from X import Y` patch 必须双向**（源头 + 本地副本） | 🟡 P1 |
| 7 | loguru 测试 | **pytest `caplog` 捕获不到 loguru** | 🟡 P1 |
| 8 | sync→async 改 | **旧测试必须同步改 `async def` + `await`** | 🟡 P1 |
| 9 | 多 Agent 拆分 | **文件零交叉时可完全并行** | 🟢 P2 |
| 10 | 截断探测 | **静默 `LIMIT` 必须多取 1 行做截断探测 + warning** | 🟡 P1 |
| 11 | 依赖声明 | **`pyproject.toml` 必须列出所有 import 的第三方包**(否则 CI 跑挂) | 🔴 P0 |

---

## 1. 写锁（`_WRITE_LOCK`）

### 硬约束

CLAUDE.md 209-213 行原文：

> **SQLite write serialization**: the sync `sqlite3` connection does NOT support
> concurrent writes from multiple coroutines. All write paths MUST hold a
> module-level `asyncio.Lock`; reads may proceed concurrently.

### 实现细节

- **锁类型**：`threading.Lock`（不是 `asyncio.Lock`）—— 原因：scheduler tick 用
  `asyncio.run()` 每次创建新 event loop，`asyncio.Lock()` 首次 acquire 绑定循环会失效；
  `threading.Lock` 跨循环安全。
- **定义位置**：`backend/services/collection_service.py:21`
- **导入路径**：`from backend.services.collection_service import _WRITE_LOCK`

### 标准范式（参考 `create_transaction`）

```python
def my_write_method(self, ...):
    with _WRITE_LOCK:                    # 锁在最外层
        with get_db() as conn:           # context manager 在锁内
            # SELECT 校验读
            # INSERT / UPDATE / DELETE
            return result
```

复杂路径（需显式 commit/rollback）参考 `update_transaction` / `delete_transaction`：
```python
with _WRITE_LOCK:
    conn = get_connection_sync()
    try:
        # ... 写操作 ...
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

### 历史教训

| 轮次 | 漏锁方法 | 后果 |
|------|---------|------|
| 第 4 轮 | portfolio 5 个写端点（`create_account` / `update_account` / `delete_account` / `update_transaction` / `delete_transaction`） | 用户 P&L 串号 |
| 第 6 轮 | `report_service.generate_reports` | 报告生成竞态 |
| 第 6 轮 | `news_service.collect_news` | 新闻重复入库 |
| 第 8 轮 | `_run_cleanup` | cleanup 期间被新写打断 |
| 第 12 轮 | `create_account` / `update_account` / `delete_account` | check-then-act 漏窗（已修复） |

### 自我检查清单

- [ ] 新增 Service / 新增写端点 → 第一件事加 `with _WRITE_LOCK:`
- [ ] 启动期一次性写（如 `_check_neo_data_token_on_startup` 写 run_logs）也建议加锁
  （第 12 轮补登）

---

## 2. UI / 模块分层

### 硬约束（CLAUDE.md 197-207 行）

```python
backend/collectors/  → ONLY module that calls external data sources
backend/services/    → business logic orchestration
backend/storage/     → database read/write + init schema
backend/scheduler/   → ONLY module that registers APScheduler jobs
backend/main.py      → FastAPI entry
ui/                  → Streamlit pages; NEVER touches DB directly
```

### 关键规则

- **UI 必须走 FastAPI**（`ui/api_client.py`），绝不能直接 import `backend/storage/`
- 跨层 import 是部署期地雷：UI 与 backend 用不同 venv/进程时会立即炸

### 自我检查清单

- [ ] `ui/*.py` 是否有 `from backend.storage import ...` 或 `from backend.storage.database import ...`？
  → 有则违规
- [ ] UI 是否直接打开 SQLite 文件？
  → 是则违规

---

## 3. 文档同步

### Task Completion Checklist 第 3 步（CLAUDE.md）

> 端点签名、状态码、字段名 3 处任一变动 → 同步更新 `docs/api/*.md`

### 易漂移点

| 改动 | 必须同步 |
|------|---------|
| 新增/修改端点路径 | `docs/api/{domain}.md` 端点列表 |
| 修改 Pydantic 字段名 | `docs/api/{domain}.md` 字段说明 |
| 修改 HTTP 状态码 | `docs/api/{domain}.md` 状态码表 |
| 修改表结构 | `docs/architecture.md` 核心表清单 + `backend/storage/schema.py` |

### 历史教训

- 第 4-7 轮：发现 30+ 处 doc/code drift
- 第 10 轮：Agent 3 专门做 7 doc 校准 + 30+ 处状态码修正

### 自我检查清单

- [ ] 改完 `backend/api/*.py` 后，相应 `docs/api/*.md` 是否同步？
- [ ] 改完 `backend/storage/schema.py` 后，`docs/architecture.md` 是否同步？

---

## 4. evidence-driven AI

### 硬约束（CLAUDE.md 149-161 行）

- `EvidenceBuilder.build(symbol)` 只组装**真实采集**的证据
- AI 输出必须含 `data_used` 字段，列出每个引用源 + 采集时间
- 不允许 hallucinate 分析

### evidence 数据消费规则（避免误导）

每个 `_check_*` 方法消费的 evidence 必须**与标的强相关**：

| ❌ 错误（与 symbol 无关） | ✅ 正确（与 symbol 强相关） |
|--------------------------|--------------------------|
| `_check_sector_context` 用市场级板块数据给每只标的同分（+0.05 bull + +0.05 bear，恒等抵消） | 改为 no-op，板块数据仅作 `data_used` 审计字段，不参与评分 |
| 用"今日大盘背景"作为某只银行股的看多理由 | 仅在能关联到该标的所属板块时评分 |

第 12 轮修复：`_check_sector_context` 移除评分（`ai_analyzer.py:471-498`），仅展示。

### 静默截断红线

任何 `LIMIT N` 截断都必须有截断探测：

```python
# 错误（静默丢失）
cursor = await conn.execute("... LIMIT 5000")
rows = await cursor.fetchall()

# 正确（多取 1 行 + warning + 截断）
cursor = await conn.execute("... LIMIT 5001")
rows = await cursor.fetchall()
if len(rows) > 5000:
    logger.warning("命中 LIMIT 5000 截断,共 {} 行可能未参与评分", len(rows) - 5000)
    rows = rows[:5000]
```

第 12 轮发现：`build_multi` 拉 news 用 `LIMIT 5000` 静默截断，已修复（`evidence_builder.py:425-441`）。

---

## 5. Provider 关闭（MRO 陷阱）

### 教训来源

第 12 轮 CRITICAL bug：`StructuredProvider.close()` / `NewsProvider.close()` 调用
`await super().close()`，在 MRO 不含 `_HttpClientMixin` 的子类（`WeStockProvider` /
`TencentNewsProvider`）上抛 `AttributeError: 'super' object has no attribute 'close'`。

### 经验

**`_HttpClientMixin` 自身是叶子节点（不调 super）**。MRO 含 mixin 的子类
（如 `SinaProvider(StructuredProvider, _HttpClientMixin)`）调用 `close()` 时
Python 直接解析到 mixin 的 `close()`，无需 base 沿 MRO 链转发。

### 修复范式（已采用，方案 B - pass no-op）

```python
class StructuredProvider(ABC):
    async def close(self) -> None:
        """关闭底层连接（默认空操作，子类可按需覆盖）。

        默认实现 no-op；子类有需要可 override。注：``_HttpClientMixin`` 已
        自身实现 close()（叶子节点，不调 super），MRO 含 mixin 的子类
        （如 ``SinaProvider``）调用 close() 时 Python 直接解析到 mixin
        版本，无需本方法沿 MRO 链转发。
        """
        return None
```

### 未来扩展 Provider 时的检查

新 Provider 决定是否需要 `close()` 行为：

| 是否继承 `_HttpClientMixin` | close() 行为 | 需要 override？ |
|------------------------------|-------------|----------------|
| Yes | mixin 关闭 httpx client | 不需要（继承即可） |
| No，但持有自己的资源（如 `NeoDataProvider` 持 `NeoDataClient`） | 自定义关闭逻辑 | **需要** |
| No，无资源（如 `WeStockProvider` / `TencentNewsProvider`） | no-op | 不需要 |

### 自我检查清单

- [ ] 新 Provider 是否有自己的资源需要关闭？
  - 是 → 自己 override `close()`
  - 否 → 不动（继承 no-op 默认实现）
- [ ] 是否调用了 `await super().close()`？
  - 是 → 警告：可能 AttributeError。改 `return None` 或具体资源释放

---

## 6. 锁测试（`_ObservableLock`）

### 难点

`from X import Y` 在导入时已绑定本地副本。如果测试只 patch 源头的 `_WRITE_LOCK`，
本地副本仍指向旧对象，导致测试无效。

### 范式（参考 `test_update_transaction_uses_write_lock`）

```python
class _ObservableLock:
    """包装 threading.Lock，记录持有次数。"""
    def __init__(self, real_lock):
        self._real = real_lock
        self.held_count = 0
    def __enter__(self):
        self.held_count += 1
        return self._real.__enter__()
    # ... 完整实现见 tests/services/test_portfolio_service.py
```

测试用法：
```python
def test_xxx_uses_write_lock(monkeypatch):
    obs_lock = _ObservableLock(threading.Lock())
    # 双向 patch：源头 + 本地副本
    monkeypatch.setattr("backend.services.collection_service._WRITE_LOCK", obs_lock)
    monkeypatch.setattr("backend.services.portfolio_service._WRITE_LOCK", obs_lock)
    # 调 service 方法
    service.create_account(...)
    assert obs_lock.held_count == 1
```

### 参考

- `tests/services/test_portfolio_service.py:964-1011` 完整 `_ObservableLock` 实现
- 现有用法：`test_update_transaction_uses_write_lock` / `test_delete_transaction_uses_write_lock`

---

## 7. loguru 测试（无 `caplog` 桥接）

### 难点

loguru 默认**不桥接 stdlib `logging`**，pytest 的 `caplog` fixture **捕获不到** loguru 输出。
如果测试断言 `logger.warning("...")` 被调用过，`caplog` 拿不到。

### 范式

```python
import loguru
from loguru import logger as _loguru_logger

def test_xxx_warning_emitted():
    captured: list[str] = []
    # loguru add() 接受可调用对象，每条日志调一次
    handler_id = _loguru_logger.add(lambda msg: captured.append(str(msg)))
    try:
        # 触发 warning 的代码
        await EvidenceBuilder.build_multi(["hk00700"])
        # 验证
        assert any("5000" in m and "news" in m.lower() for m in captured)
    finally:
        _loguru_logger.remove(handler_id)
```

### 注意事项

- `handler_id = logger.add(...)` 必须在 try 内，否则 lambda 不会清理
- 必须在 `finally` 块 `logger.remove(handler_id)`，否则 sink 累积污染后续测试

### 参考

- `tests/services/test_evidence_builder.py::TestBuildMultiTruncation::test_build_multi_news_warning_on_truncate`
  完整实例

---

## 8. sync → async 改动时旧测试同步改

### 难点

把同步函数改 `async def` 后，旧的同步测试调用会得到一个 coroutine 对象而非执行结果。
Python 会发 `RuntimeWarning: coroutine ... was never awaited`，但测试不会失败（因为不
assert 返回值），导致"测试通过但功能已坏"的假象。

### 范式

```python
# 旧测试（错误的 pass-through）
def test_xxx():
    _check_neo_data_token_on_startup()  # 实际返回 coroutine，未 await
    # ... 无 assertion → 测试 PASS 但实际未执行

# 修复后
@pytest.mark.asyncio
async def test_xxx():
    await _check_neo_data_token_on_startup()  # 正确 await
    # ... 验证 ...
```

### 同步检测

```bash
# 找所有调用目标函数的位置
grep -rn "目标函数名(" tests/ backend/

# 找 pytest 标记为 asyncio_mode="auto" 的项目里
# 如果旧测试用 def 而非 async def，可能是漏改
grep -rn "^def test_" tests/ | xargs grep -l "目标函数名"
```

### 第 12 轮教训

`_check_neo_data_token_on_startup` 改 async 后：
- `tests/test_scheduler.py::test_check_writes_utc_timestamps` 改 `async def`
- `tests/test_scheduler_health.py` 4 个测试改 `async def`
- 否则 `RuntimeWarning: coroutine ... was never awaited`

### 自我检查清单

- [ ] 函数签名 `def` → `async def` 后，grep 所有调用点
- [ ] 每个调用点要么 `await` 要么包到 `asyncio.run()`
- [ ] pytest 测试若是 `def` 而非 `async def`，改 `async def` + 加 `@pytest.mark.asyncio`
  （或在 `pyproject.toml` 已配 `asyncio_mode = "auto"` 时无需标记）

---

## 9. 多 Agent 任务划分

### 适用场景

第 12 轮用 4 个子 Agent 并行修复 11 条 bug（1 CRITICAL + 5 MAJOR + 3 MINOR + 2 NIT），
子 Agent 间文件零交叉，4 个并发跑，488/488 测试全过。

### 划分原则

1. **按文件划分**：每个子 Agent 改动的文件集合互不重叠
2. **共享工具/资源可加锁**：如 `_WRITE_LOCK` 跨文件共享，但子 Agent 各自改的是加锁，
   不修改锁本身
3. **每个子 Agent 自验后回报**：报告 ruff + pytest 结果，主 Agent 全量复验

### 主 Agent 责任

- 调度（不亲自改代码）
- 接收子 Agent 报告，检查 diff 是否符合预期
- 全量 ruff + 全量 pytest 收尾
- 从 ISSUES.md 删除已修条目 + 写归档文件
- git commit（建议拆 fix + docs 两 commit）

### 范式

```
主 Agent（监督）
├── 子 Agent A（文件集 X）→ ruff + pytest 子集 → 报告
├── 子 Agent B（文件集 Y）→ ruff + pytest 子集 → 报告
├── 子 Agent C（文件集 Z）→ ruff + pytest 子集 → 报告
├── 子 Agent D（文件集 W）→ ruff + pytest 子集 → 报告
└── 收尾：全量 ruff + pytest + 删除 ISSUES + commit
```

### 不适用场景

- 改一个文件需要 3+ 处相互依赖的修改（一个子 Agent 更合适）
- 共享复杂数据结构定义（schema、enum 等）时容易冲突

---

## 10. 静默截断探测

### 原则

任何 SQL/Python 端的 `LIMIT N` / `[:N]` 截断都可能掩盖数据丢失。

### 检查清单

- [ ] `LIMIT N` 后面有截断探测吗？`LIMIT N+1` + `if len(rows) > N: warning`？
- [ ] Python 端累加 dict/list 后只取前 N 条，前面是"无截断累加"还是"提前 continue"？
  - "先 append 再 `if len >= N: continue`" 是**错误**模式（`continue` 不阻止下一行）
  - 正确：`if len >= N: continue` 然后 `append`，或 `setdefault` + 提前 `continue`

### 第 12 轮教训

**`continue` 不截断** bug（`EvidenceBuilder.build_multi`）：

```python
# 错误
for row in cursor.fetchall():
    sym = row["symbol"]
    if sym not in klines_by_symbol:
        klines_by_symbol[sym] = []
    klines_by_symbol[sym].append(r)        # 先 append
    if len(klines_by_symbol[sym]) >= 60:
        continue                            # 只跳过本轮，下一轮又 append

# 正确
for row in cursor.fetchall():
    sym = row["symbol"]
    bucket = klines_by_symbol.setdefault(sym, [])
    if len(bucket) >= 60:
        continue
    bucket.append(r)
```

实验验证：错误版本 `len = 200`，正确版本 `len = 60`。

### `[:N]` 切片兜底不可靠

`[:60]` 在下游"兜底"看似正确，但：
- 浪费内存 20 倍（1200 行保留但只用 60）
- 维护者读代码会误解为"该 dict 有上限"
- 批量场景（100 标的 × 1200 行）Python list 内存爆炸

**修源头**比**依赖下游切片**更可取。

---

## 11. 依赖声明（pyproject.toml 完整性）

### 教训来源

第 12 轮推送后 CI 失败：`backend/collectors/rss.py:2 import feedparser`
抛 `ModuleNotFoundError`，21 个测试模块 collect 阶段中断，pytest 退出码 2。
根因：`pyproject.toml::dependencies` 漏声明 `feedparser`。

### 为什么会发生

- 本地 `.venv` 曾经手动 `pip install` 过 `feedparser`，所以本地 `pytest` 能跑通
- 但 CI 跑 `uv sync --frozen` 严格按 `pyproject.toml` 解析，不装本地"额外"的包
- 出现**本地能跑 / CI 跑挂**的诡异现象

### 规则

> **任何 `backend/` / `ui/` / `tests/` 下 `import` 的第三方包都必须显式声明在
> `pyproject.toml::dependencies` 或 `[dependency-groups].dev` 中。**
> 依赖既不能"我本地装过就行"，也不能"CI 装一下试试"。

### 自检方法

在干净环境复现（模拟 CI）：
```bash
# 删除本地 venv
rm -rf .venv

# 重新同步（应只装 pyproject.toml 列出的）
uv sync --frozen

# 跑测试
uv run pytest tests/ -q
```

如果本地能跑通而 CI 失败，**100% 是 pyproject.toml 漏声明**。

### 扫描工具（一次扫净未声明的依赖）

```python
import sys, re, pathlib

declared = {...}  # 填入 pyproject.toml 已声明的包名
externals = set()
for d in ['backend', 'tests', 'ui']:
    for p in pathlib.Path(d).rglob('*.py'):
        for m in re.finditer(r'^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)', p.read_text(encoding='utf-8', errors='ignore'), re.M):
            mod = m.group(1).split('.')[0]
            if mod not in sys.stdlib_module_names and mod not in declared and mod not in {'backend', 'tests', 'ui'}:
                externals.add(mod)
print(sorted(externals))
```

### 常见易漏的"传递依赖"陷阱

- 装了 `fastapi` 但忘了 `starlette`（实际 fastapi 传递安装，不影响）
- 装了 `pyyaml` 但 import 名是 `yaml`（声明名 = `pyyaml`）
- 装了 `feedparser` 但漏声明（**真实案例**）

### 同类陷阱：测试 db 隔离

不只是依赖：**测试运行时需要的 db 状态（schema / fixture 数据）也必须在测试自身
中显式建好**，不能依赖"前面跑过的测试碰巧建过表"或"dev venv 残留 db 文件"。

**真实案例**：`tests/scheduler/test_jobs.py::test_neodata_health_log_writer_holds_write_lock`
曾因 dev venv 残留 `data/marketlens.db`（含 `run_logs` 表）而本地能跑，CI 干净 venv
报 `sqlite3.OperationalError: no such table: run_logs`。

**规则**：
- 直接调 db 写路径的测试，**必须**用 `tmp_path` 隔离 + `init_db_sync` 显式建表
- 不要复用前一个测试的副作用（即使 conftest 有 fixture，也要走自己的 db 路径）
- 模拟 CI 干净环境验证：`rm data/*.db && uv run pytest tests/ -q` 应全过

### 原则

任何 SQL/Python 端的 `LIMIT N` / `[:N]` 截断都可能掩盖数据丢失。

### 检查清单

- [ ] `LIMIT N` 后面有截断探测吗？`LIMIT N+1` + `if len(rows) > N: warning`？
- [ ] Python 端累加 dict/list 后只取前 N 条，前面是"无截断累加"还是"提前 continue"？
  - "先 append 再 `if len >= N: continue`" 是**错误**模式（`continue` 不阻止下一行）
  - 正确：`if len >= N: continue` 然后 `append`，或 `setdefault` + 提前 `continue`

### 第 12 轮教训

**`continue` 不截断** bug（`EvidenceBuilder.build_multi`）：

```python
# 错误
for row in cursor.fetchall():
    sym = row["symbol"]
    if sym not in klines_by_symbol:
        klines_by_symbol[sym] = []
    klines_by_symbol[sym].append(r)        # 先 append
    if len(klines_by_symbol[sym]) >= 60:
        continue                            # 只跳过本轮，下一轮又 append

# 正确
for row in cursor.fetchall():
    sym = row["symbol"]
    bucket = klines_by_symbol.setdefault(sym, [])
    if len(bucket) >= 60:
        continue
    bucket.append(r)
```

实验验证：错误版本 `len = 200`，正确版本 `len = 60`。

### `[:N]` 切片兜底不可靠

`[:60]` 在下游"兜底"看似正确，但：
- 浪费内存 20 倍（1200 行保留但只用 60）
- 维护者读代码会误解为"该 dict 有上限"
- 批量场景（100 标的 × 1200 行）Python list 内存爆炸

**修源头**比**依赖下游切片**更可取。

---

## 附录 A：经验索引（按发现轮次）

| 轮次 | 经验 | 归档位置 |
|------|------|---------|
| 第 4 轮 | portfolio 5 个写端点漏锁 → 必须 `_WRITE_LOCK` 包裹所有写路径 | 本文件 §1 |
| 第 4-7 轮 | doc/code drift 30+ 处 → 改后端必动 docs/api | 本文件 §3 |
| 第 6/8 轮 | `report_service` / `news_service` / `_run_cleanup` 漏锁补登 | 本文件 §1 |
| 第 8 轮 | 资金主线 8 个 CRITICAL 修复 | `docs/dev/issues_2026-06-08.md` |
| 第 10 轮 | 7 doc 校准 + 30+ 处状态码修正 | `docs/dev/issues_2026-06-08.md` |
| 第 11 轮 | `ISSUES.md` 迁移（`CODE_REVIEW.md` → `ISSUES.md`）+ git mv 保 history | `docs/dev/issues_2026-06-08.md` |
| 第 12 轮 | `Provider.close()` AttributeError → 改 pass no-op | 本文件 §5 |
| 第 12 轮 | `build_multi` 累加无截断 → `setdefault` + 提前 `continue` | 本文件 §10 |
| 第 12 轮 | `news LIMIT 5000` 静默截断 → 多取 1 行探测 | 本文件 §10 |
| 第 12 轮 | `_check_sector_context` 与 symbol 无关 → 改 no-op | 本文件 §4 |
| 第 12 轮 | loguru `caplog` 桥接缺失 → 用 `logger.add(lambda)` | 本文件 §7 |
| 第 12 轮 | sync 改 async 时旧测试 `RuntimeWarning` | 本文件 §8 |
| 第 12 轮 | 锁测试需 patch 双向 | 本文件 §6 |
| 第 12 轮 | 多 Agent 文件零交叉可完全并行 | 本文件 §9 |
| 第 12 轮 | `pyproject.toml` 漏声明 `feedparser` → CI 跑挂(本地能跑过是假象) | 本文件 §11 |

---

## 附录 B：相关文档链接

- **CLAUDE.md** — 项目硬约束、架构、命令、Task Completion Checklist
- **ISSUES.md** — 当前活跃 issue tracker（修完即删）
- **docs/dev/issues_2026-06-08.md** — 第 4-11 轮 70+ 条审查+修复历史
- **docs/dev/issues_2026-06-08_r12.md** — 第 12 轮 11 条 + 修复归档
- **docs/dev/pre-commit.md** — pre-commit 钩子使用指南
- **docs/architecture.md** — 架构文档（与本文件互补）
- **docs/api/*.md** — 端点 API 文档（7 份）
