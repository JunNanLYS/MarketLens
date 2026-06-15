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
| 12 | 端口清理 | **自残保护 + 10s 硬超时**（不允许 silent 启动） | 🟡 P1 |
| 13 | 路由动画 | **只用入场动画**（`initial` + `animate`），不用 `AnimatePresence + exit` | 🟡 P1 |
| 14 | WeStock 调子进程 | **PowerShell + 全局 wrapper**，避开 `npx` / 裸 `node` / sh wrapper | 🟡 P1 |
| 15 | ConfigStore 白名单 | **PATCH 端点必须白名单 key 列表**（`name`/`provider`/`optional` 不接受覆盖） | 🟡 P1 |
| 16 | Issue tracker | **新问题只写 `ISSUES.md`，禁建 `CODE_REVIEW.md`** | 🟡 P1 |
| 17 | API 成本防御 | **第三方付费 API 路径必须有 autouse 拦截**（不依赖每个测试自觉） | 🔴 P0 |
| 18 | UI 重构流程 | **五阶段顺序**：DESIGN.md → token → shared → pages → 验证 | 🟡 P1 |
| 19 | Squash-merge 后合并 | **优先 cherry-pick 而非 rebase**（保留独立 commit identity） | 🟢 P2 |
| 20 | 写锁源单一化 | 共享 `_WRITE_LOCK` 必须有中立模块,新 mixin/新 Service 只能从那里导入 | 🔴 P0 |
| 21 | 审计完整性 | **任何**调度任务结尾都要在锁内写 `run_logs`;无 URL 数据也要有去重键 + raw_data | 🟡 P1 |
| 22 | 路由入口契约 | URL 携带状态(`?key=...`)时,React 页面要 `useSearchParams` 同步,别只信本地 state | 🟡 P1 |

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
- **锁源（2026-06-15 收口）**：唯一权威定义在
  [`backend/services/_write_lock.py`](../../backend/services/_write_lock.py)：
  ```python
  """SQLite 同步写入共享锁。"""
  import threading
  _WRITE_LOCK: threading.Lock = threading.Lock()
  ```
  `backend/services/collection_service.py` 在 `__all__` 里 re-export 一份 `_WRITE_LOCK`，
  以兼容 `from backend.services.collection_service import _WRITE_LOCK` 旧路径。
- **导入路径（任选其一）**：
  - `from backend.services._write_lock import _WRITE_LOCK`（推荐，中立）
  - `from backend.services.collection_service import _WRITE_LOCK`（兼容）
- **禁止**：在 `asset_service.py` / `_collection/_core.py` / 任何其它模块私有化
  `threading.Lock()`。混用会变成"两把锁都加锁 → 实际互不感知"，是 r15 资金写端点
  漏锁根因。

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
frontend/            → React + Vite UI; NEVER touches DB directly
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

## 12. 端口自动清理（fail-loud + 自残保护）

### 教训来源

第 13 轮（2026-06-13）—— `scripts/launcher.py` 第二次启动时，前一次未退干净导致 8000 端口被占，**用户被迫手动打开任务管理器**。

### 经验

1. **探测 → 查 PID → kill → 轮询等待**，四步串行，缺一不可
2. **自残保护**：PID == 启动器自身时拒绝清理（`os.getpid()` 比较），避免自杀
3. **超时硬约束**：200ms 轮询 × 50 次 = 10s 上限，超时抛 `RuntimeError`（**禁止 silent 启动**——用户看到错误才知道手动关进程）
4. **平台分支**：Windows `netstat -ano -p tcp` + `taskkill /PID <pid> /T /F`（/T 杀子进程）；Unix `lsof -ti tcp:<port>` + `os.kill(pid, SIGTERM)`。**lsof 不存在时返回空 set**，让上层抛错而不是猜（猜错会误杀无关进程）
5. **测试 patch 隔离**：mock `_port_pids` / `_is_port_available` / `_terminate_pid` 三个边界点，避免真实占用端口

### 范式（参考 `tests/scripts/test_launcher.py`）

```python
with patch("scripts.launcher._port_pids", return_value={1234}), \
     patch("scripts.launcher._terminate_pid") as mock_terminate, \
     patch("scripts.launcher._is_port_available", side_effect=[False, True]):
    _release_port("127.0.0.1", port, "FastAPI 后端")
mock_terminate.assert_called_once_with(1234, "FastAPI 后端")
```

### 自我检查清单

- [ ] 自残保护（PID == `os.getpid()`）
- [ ] 10s 硬超时 + `RuntimeError` 而非静默继续
- [ ] `/T` 杀子进程（Windows）
- [ ] `lsof` 不存在时优雅降级为"查不到 PID → 抛错"
- [ ] 测试 mock 三个边界点，不真占用端口

---

## 13. AnimatePresence 退出动画的"空白陷阱"

### 教训来源

第 13 轮（2026-06-13）—— `AppLayout.tsx` 用 `AnimatePresence` + `mode="wait"` 给路由切换加淡入淡出。**快速点击导航时**：
- v1：无 `mode="wait"` → 旧页 + 新页纵向堆叠（视觉上"内容跑到底下"）
- v2：加 `mode="wait"` → 退出动画未完成时点击下一路由 → 新页挂起等待 → 全部空白

### 经验

1. **AnimatePresence 的退出动画 = DOM 状态机**：`mode="wait"` 让旧元素 exit 完再 mount 新元素；快速切换时排队卡死
2. **路由切换的"内容永远在" 优先于"好看"**：用 `key={location.pathname}` 的单 `motion.div` + **仅入场动画**（`initial` + `animate`，无 `AnimatePresence` 包裹），DOM 切换是原子的
3. **HMR 假错误**：删 `AnimatePresence` 导入时，Vite HMR 偶发报 `AnimatePresence is not defined`，**reload 页面**后正常（不要去 code 找 bug）

### 范式

```tsx
// 错误：AnimatePresence + mode="wait" 快速切换会空白
<AnimatePresence mode="wait">
  <motion.div key={path} exit={{ opacity: 0 }}>...</motion.div>
</AnimatePresence>

// 正确：单 keyed motion.div + 仅入场
<motion.div
  key={location.pathname}
  initial={reduceMotion ? false : { opacity: 0 }}
  animate={{ opacity: 1 }}
  transition={{ duration: 0.08, ease: "linear" }}
>
  <Outlet />
</motion.div>
```

### 自我检查清单

- [ ] 路由级动画只用入场（`initial` + `animate`），不用 `exit`
- [ ] 不依赖 `AnimatePresence` 串行化（key 改变就是原子替换）
- [ ] 删除 import 后 reload 验证（避免 HMR 假错）

---

## 14. WeStock 调子进程：Node CSPRNG 的三路径绕开

### 教训来源

第 13 轮（2026-06-13）—— `westock-data-clawhub` CLI 在 Windows + Node 24 上偶发 `ncrypto::CSPRNG` 断言失败（rc=134），100% 撞到。

### 经验

**三种调用路径都会失败，必须全避开**：

1. ❌ `npx -y westock-data-clawhub@1.0.4` —— 每次冷启动新 Node 进程，触发 CSPRNG 初始化
2. ❌ Python `subprocess.run(["node", ...])`（MSYS 环境下的 Python）—— MSYS 干扰 Node 父进程栈
3. ❌ npm 全局装的 sh wrapper（用 `sed`/`dirname`/`uname`）—— 精简 PATH 下 exit 1

**唯一稳的路径**：先 `npm i -g westock-data-clawhub@1.0.4`，然后 `backend/collectors/westock.py::_run_cli` 走：

```python
subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command",
     f"& '{wrapper_path}' {subcommand} {args}"],
    capture_output=True, text=True, timeout=..., check=False,
)
```

- PowerShell 7 优先于 Windows PowerShell 5.1
- `env` 透传父进程（**不裁剪**）—— PowerShell 需要 PATHEXT/PATH 解析 wrapper
- `package_name` 进 `config.yaml` 字段，升级改 yaml 不改 code

### 自我检查清单

- [ ] WeStock 不走 `npx` / 裸 `node` / sh wrapper
- [ ] 走 PowerShell 调全局 wrapper
- [ ] `env` 透传不裁剪
- [ ] `package_name` 字段在 yaml 而非硬编码

---

## 15. ConfigStore 白名单：避免误改 security/api_key

### 教训来源

第 12 轮（2026-06-11）—— `Settings` PATCH 端点开放任意 key 改写能力，理论可改 `security.api_key`，**单用户工具也会自伤**（改错后所有写端点鉴权全挂）。

### 经验

1. **白名单 > 黑名单**：明确列出可改 key（`data_sources.*` / `scheduler.tasks.*`），其他 key 全部 400 拒绝
2. **保留字段强制覆盖**：`name` / `provider` / `optional` 在 PATCH 时被服务端强制保留，不接受前端覆盖（避免破坏 Provider 类路由）
3. **原子写回 + 备份**：先 `tempfile + os.replace`，写前 `shutil.copy2(yaml, yaml.bak)`（不是 `copy` —— 保留 mtime）
4. **回滚端点独立**：`POST /settings/rollback` 必须存在，作为改错的逃生通道
5. **reload 钩子单向同步**：ConfigStore 改 → 触发 Provider 链 / APScheduler reschedule，**不要反向**（Provider 内部状态变化不应写回 yaml）

### 范式（参考 `backend/config_runtime.py`）

```python
ALLOWED_KEYS = re.compile(r"^(data_sources\.(structured|news)\.[a-z0-9_]+|scheduler\.tasks\.[a-z_]+\.(interval|cron))$")
PRESERVE_KEYS = {"name", "provider", "optional"}

def update_with_special_handling(self, updates: dict) -> dict:
    for key in updates:
        if not ALLOWED_KEYS.match(key):
            raise ConfigStoreError(f"key '{key}' 不在白名单内")
    # ... atomic write + backup + reload hook
```

### 自我检查清单

- [ ] PATCH 端点有白名单（不允许任意 key）
- [ ] `name` / `provider` / `optional` 不接受 PATCH 覆盖
- [ ] 写前 `shutil.copy2` 备份到 `.bak`（保 mtime）
- [ ] `tempfile + os.replace` 原子写回
- [ ] 存在独立的 rollback 端点
- [ ] reload 钩子单向（yaml → runtime，**不**反向）

---

## 16. Issue tracker 唯一合法位置是 `ISSUES.md`

### 教训来源

第 15 轮（2026-06-11）—— 审查完 37 条 UI 问题后，习惯性地写到了 `CODE_REVIEW.md`，
**用户立刻纠正**：

> "我记得不是写到 @ISSUES.md 当中吗？你怎么写到 @CODE_REVIEW.md 当中了"

CLAUDE.md 项目状态段明文：

> "第 11 轮 `git mv` `CODE_REVIEW.md` → `ISSUES.md` 保留 history。"

**禁止新建 `CODE_REVIEW.md`** — 11 轮已合并到 ISSUES.md，再创建就是历史回退。

### 规则

> **新发现的 issue 只能写到 `ISSUES.md` 的"已知问题登记"** 段，修复后从该段删除
> 归档到 `docs/dev/issues_<修复日期>.md`。
>
> **绝不再创建 `CODE_REVIEW.md`**。如果看到旧 `CODE_REVIEW.md` 残留 → `git rm` 删除。

### 自我检查清单

- [ ] 新问题写进 `ISSUES.md` 而非 `CODE_REVIEW.md`
- [ ] 修复完 issue 从 `ISSUES.md` 段删除，归档到 `docs/dev/issues_*.md`
- [ ] 看到 `CODE_REVIEW.md` 残留 → 立即 `git rm`（不写修复记录）

---

## 17. 用户对第三方 API 成本敏感 → 测试必须 mock 真实端点

### 教训来源

第 16 轮（2026-06-12）—— 修复 AI 报告页 TypeScript 类型时，担心测试可能真调
DeepSeek API。用户原话：

> "在测试中是不是有真实调用DeepSeek的API，如果有请改成虚拟的，因为这会消耗的我钱。"

**这是一个真约束，不是性能问题**。DeepSeek API 按 token 计费，562 测试每次跑会
消耗真实配额。

### 现状

- 现有测试通过 `analyzer._client = AsyncMock()` 注入确定性响应
- `DeepSeekSentimentAnalyzer._get_client()` 在 `api_key == ""` 时早返回 `_available=False`
- 工厂层 + 测试 fixture 双层保护

### 防御性加固（2026-06-12）

`tests/conftest.py` 加 **autouse fixture**，作为最后一道防线：

```python
@pytest.fixture(autouse=True)
def _block_real_deepseek_calls(monkeypatch):
    """防御性：禁止测试中真实调用 api.deepseek.com。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from backend.services.sentiment.deepseek_analyzer import DeepSeekSentimentAnalyzer
    real_get_client = DeepSeekSentimentAnalyzer._get_client

    def guarded(self):
        client = real_get_client(self)
        if client is None:
            return None
        base_url = getattr(client, "base_url", "")
        if "api.deepseek.com" in str(base_url).lower():
            raise RuntimeError("禁止真实调用 api.deepseek.com — conftest.py 拦截")
        return client

    monkeypatch.setattr(DeepSeekSentimentAnalyzer, "_get_client", guarded)
```

### 规则

> **任何调用第三方付费 API 的代码路径必须有 mock 保护 + autouse 防御性 fixture。**
> 即使现有测试都 mock 了，仍要加全局 conftest 兜底——防止后续 PR 引入新测试忘记 mock。

### 自我检查清单

- [ ] 第三方付费 API 路径（DeepSeek / OpenAI / Claude / 短信 / 邮件）在测试中
      必须 `AsyncMock` / `MagicMock`
- [ ] 至少一处 **autouse fixture** 拦截真调用（不依赖每个测试的自觉）
- [ ] 拦截策略：检测 base_url / host 含真实域名时 raise RuntimeError
- [ ] 拦截时清除相关 env var（`monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)`）
- [ ] 用真实但极小的 quota 跑一次 pytest 后，看 API 控制台"无调用"才放心

---

## 18. 前端 UI 重构的"五阶段顺序"流程

### 教训来源

第 17-18 轮（2026-06-12/13）—— 用户首次提出：

> "请您先根据项目的用途设计一套设计语言输出到 DESIGN.md 中，然后再根据设计语言
> 将前端 UI 进行重构，使前端 UI 更精美独特。"

发现这个"先设计语言、后重构"的流程在大型 UI 重构中可复用，且顺序不可乱。

### 五阶段流程

```
Phase 1: 设计语言文档（DESIGN.md）    ← 必须先做，不能跳
  ↓
Phase 2: 设计令牌 + 全局样式          ← token 是基础
  ↓
Phase 3: 8 个 shared 组件            ← 原子组件先统一
  ↓
Phase 4: 7 个 page 视觉重构          ← 组合阶段
  ↓
Phase 5: 验证 + 收尾                  ← lint/type-check/build/pytest + 浏览器目视
```

### 为什么不能跳 Phase 1

- 写代码前如果没有 DESIGN.md 锚定，每个组件会"自己造 token"，风格漂移
- 用户确认 DESIGN.md 后 = 一次评审机会，比 5 轮组件 PR 评审更高效
- DESIGN.md 必须包含：color / typography / spacing / radius / elevation / motion
  6 类 token + 10+ 组件规范 + 8 状态体系 + WCAG AA 4.5:1 + 实施规则

### Phase 2 必须做

- 26 color token（4 大类：主色/强调/语义/中性，浅+深双套）
- spacing 8px 基准 6 级 + radius 4 级 + elevation 3 级 + motion 3 档
- `frontend/tailwind.config.js` 全 token 映射
- `ConfigProvider` 注入 antd token（让 antd Menu / Card / Tag 用我们的色）

### Phase 3 顺序（依赖最小化）

- 先无依赖：`PnlDisplay` / `StatusTag` / `QueryErrorState` / `ConfirmDelete`
- 再依赖：`KpiBar`（用 `PnlDisplay`）/ `CollectionTimeline`（用 `QueryErrorState`）
- 最后：layout 层 `Sidebar` / `AppLayout` / 新增 `PageHeader` 共用

### Phase 4 顺序（轻→重）

```
Settings    (最轻：3 卡片 + 表格) ← 1-2 小时
TaskStatus  (表格 + 触发)
NewsList    (列表 + 过滤)
TrackedAssets (表格 + 添加/搜索)
AiReports   (卡片 + StatusTag 改造点)
Portfolio   (3 Tab)
AssetDetail (最重：3 栏 + Hero + 图表)
```

### Phase 5 验证清单

```bash
cd frontend && npm run lint && npm run type-check && npm run build
uv run pytest tests/ -q
# 启动 dev server + 浏览器目视 7 page + light/dark
```

### 范式 — DESIGN.md 章节模板

1. 品牌定位（1 段）
2. 设计原则（5 条）
3. 设计令牌（color/typography/spacing/radius/elevation/motion 6 张表）
4. 组件库规范（10+ 组件：每个含 default/hover/active/focus/disabled/loading/error/empty 8 状态）
5. 状态体系
6. 可访问性（WCAG AA 4.5:1 / 3px focus ring / 44px 触摸目标 / reduced motion）
7. 实施规范（命名 / 何时用 antd 默认 vs 自定义 / 暗色模式 / 现状问题对照表）

### 自我检查清单

- [ ] Phase 1 完成前不写任何 frontend 代码
- [ ] Phase 2 token 完整（含暗色模式）再开始 Phase 3
- [ ] Phase 3 改 shared 组件时同步在 pages 找 import 现场改造
- [ ] Phase 4 按"轻→重"顺序，避免一上来改最重的 AssetDetail
- [ ] Phase 5 验证 4 件套全过（lint + type-check + build + pytest）才视为完成

---

## 19. Squash-merge 后的"非 fast-forward"：何时 cherry-pick，何时新建

### 教训来源

第 18 轮（2026-06-14）—— 工作流上 `claude/*` 分支通过 `gh pr merge --squash` 合并
后，main 拿到 squash commit（如 `a72835a`）。后续该分支继续累加新 commit（如
`7ccdf63`）时，`git merge --ff-only` 失败，提示"diverging branches"。

### 三种场景的正确动作

| 场景 | 特征 | 正确动作 |
|------|------|---------|
| A. 线性延续 | source 是 main 的严格后续 | `git merge --ff-only` 在主 worktree |
| B. 已 squash 后旁支延续 | source 是 main 父 commit 之后累加的新 commit | `git cherry-pick <commit>` 在主 worktree |
| C. PR 远程分支 | source 在 `origin/claude/*` | `gh pr merge <num> --squash --delete-branch` |

**主 worktree 是 `D:/Project/MarketLens`**（已 used by main），worktree 子目录
不能 checkout main，所有 main 写入必须回主 worktree。

### 决策树

```
$ git log --oneline --graph --all -10  # 看分支图
* <source_commit>   feat: ...   ← 目标 commit
* <squash_commit>   feat: ... (#N)  ← main 当前 HEAD
|/
* <base_commit>     ...
* <base_commit>     ...
```

- 如果图是线性 → `--ff-only`
- 如果 source 在 squash 之后的旁支 → `cherry-pick source_commit`
- 如果图很乱 → `git rebase main` 在 source 上，再 `--ff-only`（但 rebase 会改 source commit hash）

### 规则

> **优先 cherry-pick 而非 rebase**——rebase 改写 commit hash 会让 PR 评论与原 commit
> 失联。Cherry-pick 创建**新 commit**保留独立身份，历史可追溯。

### 自我检查清单

- [ ] 看 `git log --oneline --graph --all -10` 确认分支关系
- [ ] 主 worktree 操作 main（不在 worktree 子目录）
- [ ] 优先 cherry-pick 而非 rebase
- [ ] 合并后 `git push origin main` 推送到远程

## 20. 写锁源单一化（中立模块兜底）

### 教训来源

第 15 轮（2026-06-15）—— `AssetService` 在 `__init__` 之外有自己一把私有
`threading.Lock()` 实例。看起来"也加了锁"，但与 `collection_service._WRITE_LOCK`
是**两个对象**：

```python
# asset_service.py（旧代码，r15 已修）
_WRITE_LOCK = threading.Lock()  # ← 独立实例

# collection_service.py
_WRITE_LOCK = threading.Lock()  # ← 另一个独立实例
```

后果：
- 资金写端点（add/update/delete_asset）与采集清理（collect_quotes /
  collect_daily_close）"每条路径都加锁"，但**两边互不感知**
- 高并发下两个线程可同时进 `with _WRITE_LOCK:` 块写 SQLite → 资金主表 + 行情表
  并发写

### 经验

1. **共享锁必须有"中立模块"作为唯一定义点**。不能"谁用谁 import 后再赋一个本地变量"，
   那会变成独立实例
2. **保留兼容 re-export**：`collection_service.py` 在 `__all__` 里再 export 一份，
   让 `from backend.services.collection_service import _WRITE_LOCK` 仍可用，
   避免一次性改完所有调用点
3. **新 Service / 新 mixin 只能从 `_write_lock.py` 导入**。下次 review 看到
   `import threading; _WRITE_LOCK = threading.Lock()` 出现在 `asset_service.py` /
   `_collection/_core.py` 等非授权位置直接挡

### 范式（已采用）

```python
# backend/services/_write_lock.py
"""SQLite 同步写入共享锁。"""
import threading
_WRITE_LOCK: threading.Lock = threading.Lock()
```

```python
# 任何写路径（新 Service、新 mixin、scheduler 任务）
from backend.services._write_lock import _WRITE_LOCK
with _WRITE_LOCK:
    with get_db() as conn:
        ...
```

### 自我检查清单

- [ ] grep `threading.Lock()` 出现的非授权模块
- [ ] 写端点用 `is` 断言锁对象身份（如 `test_asset_service_uses_collection_write_lock`）
- [ ] 新 mixin / 新 Service 改用 `from backend.services._write_lock import _WRITE_LOCK`

---

## 21. 调度任务审计完整性（run_logs + 数据去重）

### 教训来源

第 15 轮（2026-06-15）—— 两个相邻但独立的缺口：

1. `backend/scheduler/jobs.py::_run_cleanup` **根本不写 `run_logs`**
2. `backend/services/news_service.py::collect_news` 的 `if url: existing_urls.add(url)`
   之前直接 `continue` → 无 URL 新闻**无限重复入库**，且 `raw_data` 只在 url 非空时落库

后者更隐蔽：人工 review 一眼看到 `existing_urls.add(url)` 觉得"已经有去重了"，
但分母是"有 url 的子集"，分子是"所有要插入的项"——一比就漏。

### 经验

1. **任何 APScheduler 任务结束都要写一条 `run_logs`**，与采集任务同模板：
   `task_name / status / started_at / finished_at / error_message / affected_assets`
2. **"成功插入后才落 raw_data" + "用业务键去重"，与 url 字段正交**。`raw_data` 是审计
   trail，不能因为 schema 缺唯一键就不写；要么构造稳定去重键，要么在 DB 层加
   `UNIQUE` 兜底
3. **去重键要稳定**——`source + normalized_title + published_at` 比 `url` 鲁棒：
   - 标题前后空格、`　` 全角空格要 normalize
   - 跨批/跨库都要命中（避免同新闻被不同 provider 采集时插入两次）

### 范式

```python
# 1. 调度任务 — 锁内写审计行
with _WRITE_LOCK:
    conn = get_connection_sync()
    try:
        # ... 业务写入 ...
        conn.execute(
            """INSERT INTO run_logs
               (task_name, status, started_at, finished_at, error_message, affected_assets)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("cleanup", status, started_at, finished_at, error_message, total_deleted),
        )
        conn.commit()
    finally:
        conn.close()

# 2. 业务去重 + 审计双写
existing_url_less_keys: set[tuple[str, str, str]] = {
    (r["source"], _norm_title(r["title"]), r["published_at"] or "")
    for r in conn.execute(
        "SELECT source, title, published_at FROM news_items WHERE url IS NULL OR url = ''"
    ).fetchall()
}
for item in news_items:
    key = (item["source"], _norm_title(item["title"]), item.get("published_at") or "")
    if key in existing_url_less_keys:
        skipped += 1
        continue
    conn.execute("INSERT INTO news_items (...) VALUES (...)", (...))
    existing_url_less_keys.add(key)  # 批内也防重
    conn.execute(
        "INSERT INTO raw_data (..., data_type, raw_json, collected_at) VALUES (..., 'news', ?, ?)",
        (json.dumps(item, ensure_ascii=False, default=str), now),
    )
```

### 自我检查清单

- [ ] 任何 scheduler 任务结尾都有 `run_logs` 行（grep `_run_` 函数体内有 `INSERT INTO run_logs`）
- [ ] 数据采集同时维护 `raw_data`（不依赖 url / 唯一键等条件）
- [ ] 去重键经过 normalize（空白、全角半角、case）
- [ ] 批内 + 跨批都防重（去重 set 在循环里 add 自身）

---

## 22. 路由入口契约（URL ↔ React state 同步）

### 教训来源

第 15 轮（2026-06-15）—— Command Palette 已经按 `?assetId=<id>` 生成跳转链接，
但 `AssetDetail` 用本地 `useState<number | null>(null)` 起步，**根本不看 URL**。
表现：用户从命令面板点开 → 路由进入详情页 → 详情页渲染"暂无数据"。

新闻页 `NewsList` 还有一个对称的反面：把 `/asset-detail/${symbol}` 当成合法路由 push，
但 React Router 只注册了 `/asset-detail`，跳转直接 404。

### 经验

1. **URL 携带的状态（`?key=...`） = 路由协议的对外契约**。所有"从其它地方跳进来"的
   入口必须把它读出来
2. **双向同步**：用户从 URL 进来 → state 派生；用户改了 state → 反向写回 URL
   （`setSearchParams`），刷新页面不会丢
3. **跳转前先 resolve 出 id**。如果其它地方只有 symbol，先调
   `GET /assets?search=<symbol>` 解析 id 再 push，避免 `/:symbol` 风格的参数化路由
   给自己埋坑
4. **`navigate()` 后要 `void` 显式吞 promise**。`void navigateToAssetSymbol(s)`
   比 `navigateToAssetSymbol(s)` 更清晰

### 范式

```tsx
// 1. URL → state（同步）
const [searchParams] = useSearchParams();
const assetIdParam = searchParams.get("assetId");
const parsedAssetId = assetIdParam ? Number(assetIdParam) : null;
const [assetId, setAssetId] = useState<number | null>(
  Number.isFinite(parsedAssetId) ? parsedAssetId : null,
);

// 2. state → URL（反向写回）
const handleAssetChange = (nextAssetId: number) => {
  setAssetId(nextAssetId);
  setSearchParams({ assetId: String(nextAssetId) });
};

// 3. 跳转前 resolve
const navigateToAssetSymbol = async (symbol: string) => {
  const { data } = await apiClient.get("/assets", { params: { search: symbol } });
  const asset = data.items.find((it) => it.symbol === symbol);
  if (!asset) {
    message.warning(`标的 ${symbol} 不在追踪列表中`);
    return;
  }
  navigate(`/asset-detail?assetId=${asset.id}`);
};
```

### 自我检查清单

- [ ] 任何"被命令面板 / 列表 / 卡片跳转打开"的页面，读 `useSearchParams`
- [ ] `setSearchParams` 与 `setState` 配对（任意方向都同步）
- [ ] 跳转链接里只有 id，不直接拼 symbol
- [ ] `navigate()` 用 `void` 显式吞 promise（或 async + 显式 await）

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
| 第 13 轮 | 启动器端口自动清理（fail-loud + 自残保护） | 本文件 §12 |
| 第 13 轮 | AnimatePresence 退出动画的"空白陷阱" → 单 keyed motion.div | 本文件 §13 |
| 第 13 轮 | WeStock Node CSPRNG 三路径绕开（PowerShell + 全局 wrapper） | 本文件 §14 |
| 第 12 轮 | ConfigStore 白名单：避免误改 security / api_key | 本文件 §15 |
| 第 15 轮 | Issue tracker 唯一合法位置是 `ISSUES.md`，禁建 `CODE_REVIEW.md` | 本文件 §16 |
| 第 16 轮 | 用户对第三方 API 成本敏感 → conftest.py 防御性拦截 DeepSeek | 本文件 §17 |
| 第 17-18 轮 | UI 重构五阶段流程（DESIGN.md → token → shared → pages → 验证） | 本文件 §18 |
| 第 18 轮 | Squash-merge 后的 cherry-pick / rebase / ff-only 选择决策树 | 本文件 §19 |
| 第 15 轮 | `AssetService` 私有锁 → 中立 `_write_lock.py` 收口 | 本文件 §20 |
| 第 15 轮 | `news_service` 无 URL 去重 / `raw_data` 漏写 / cleanup 无审计 | 本文件 §21 |
| 第 15 轮 | `AssetDetail` 不读 `?assetId=` + 跳转路由不存在的 `:symbol` 参数 | 本文件 §22 |

---

## 附录 B：相关文档链接

- **CLAUDE.md** — 项目硬约束、架构、命令、Task Completion Checklist
- **ISSUES.md** — 当前活跃 issue tracker（修完即删）
- **docs/dev/issues_2026-06-08.md** — 第 4-11 轮 70+ 条审查+修复历史
- **docs/dev/issues_2026-06-08_r12.md** — 第 12 轮 11 条 + 修复归档
- **docs/dev/issues_2026-06-11_r13.md** — 第 13 轮 React 迁移审查 27 条
- **docs/dev/issues_2026-06-11_r14.md** — 第 14 轮前端审查 6 条
- **ISSUES.md** "第 15 轮前端审查" + "第 16 轮 UI/UX" — 37 条 + 修复（合并到 PR #7）
- **docs/dev/pre-commit.md** — pre-commit 钩子使用指南
- **docs/architecture.md** — 架构文档（与本文件互补）
- **docs/api/*.md** — 端点 API 文档（7 份）

---
