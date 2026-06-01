# MarketLens Code Review

审查日期：2026-05-31
审查范围：全部 P0 后端 + UI 代码
审查方法：三轮审查（架构 → 逐文件 → 边界加固）

---

## [CRITICAL] 安全问题

### C-1: SQL 注入风险 — `tag` 筛选使用 LIKE 模糊匹配未转义通配符

**文件**: [asset_service.py:151](file:///d:/Project/MarketLens/backend/services/asset_service.py#L151)

```python
if "tag" in effective_filters:
    conditions.append("ta.tags LIKE ?")
    params.append(f"%{effective_filters['tag']}%")
```

用户输入的 `tag` 值直接嵌入 `%...%` 中，如果用户输入 `%` 或 `_` 等 SQL LIKE 通配符，会导致意外的匹配结果。虽然使用了参数化查询不会导致 SQL 注入，但 LIKE 通配符未转义会导致逻辑漏洞。

**建议**: 对用户输入中的 `%` 和 `_` 进行转义（替换为 `\%` 和 `\_`），或使用更精确的匹配方式。

---

### C-2: SQL 注入风险 — `related_symbols` 筛选使用 LIKE 模糊匹配

**文件**: [news_service.py:172-173](file:///d:/Project/MarketLens/backend/services/news_service.py#L172-L173)

```python
if "symbol" in effective_filters:
    conditions.append("related_symbols LIKE ?")
    params.append(f'%{effective_filters["symbol"]}%')
```

同 C-1，LIKE 通配符未转义。此外，`related_symbols` 存储为 JSON 数组字符串，使用 LIKE 匹配 JSON 内容不可靠——例如搜索 `hk00700` 可能误匹配到 `hk007001`。

**建议**: 使用 `json_each()` 解析 JSON 数组后精确匹配，或在 `news_items` 表增加关联表实现多对多关系。

---

### C-3: `_match_symbols` 中 `symbol in text` 匹配过于宽泛

**文件**: [news_service.py:143](file:///d:/Project/MarketLens/backend/services/news_service.py#L143)

```python
if symbol in text:
    matched.append(symbol)
```

简单的子字符串匹配会导致误匹配。例如新闻中出现 `sh600519` 会误匹配到 `sh60051`（如果存在该标的）。

**建议**: 使用正则表达式加词边界匹配，或对 symbol 前缀+代码做更严格的匹配。

---

## [MAJOR] 正确性问题

### M-1: `_get_current_holding` 中 split 计算逻辑错误

**文件**: [portfolio_service.py:105-119](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L105-L119)

```python
elif row["type"] == "split":
    total *= row["quantity"]
```

当存在多笔不同标的的交易时，`_get_current_holding` 查询了 `account_id + symbol` 的所有交易，但 split 的 `quantity` 表示拆股比例（如 2 表示 1 拆 2）。如果同一标的有先 buy 再 split 的交易，`total *= quantity` 是正确的。但如果交易列表中包含其他类型的交易，乘法操作会基于当前累计值计算，这在混合 buy/sell/split 场景下可能产生错误结果。

例如：buy 100 → sell 50 → split 2，正确结果应为 (100-50)*2=100，但当前逻辑：0+100=100 → 100-50=50 → 50*2=100，结果正确。但如果顺序是 buy 100 → split 2 → sell 50，正确结果应为 100*2-50=150，当前逻辑：0+100=100 → 100*2=200 → 200-50=150，也正确。

**结论**: 当前逻辑在按时间排序的情况下是正确的，但 `_get_current_holding` 方法未按 `trade_date` 排序查询，可能导致交易顺序错误。

**建议**: 在查询中添加 `ORDER BY trade_date, created_at` 确保按时间顺序计算。

---

### M-2: `_get_current_holding` 和 `_get_current_holding_from_conn` 重复代码

**文件**: [portfolio_service.py:105-119](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L105-L119) 和 [portfolio_service.py:175-190](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L175-L190)

两个方法逻辑完全相同，只是一个使用外部连接，一个使用传入连接。`_get_current_holding` 方法未被使用（`create_transaction` 调用的是 `_get_current_holding_from_conn`）。

**建议**: 删除未使用的 `_get_current_holding` 方法，保留 `_get_current_holding_from_conn`。

---

### M-3: `collect_quotes` 中 `affected_assets` 记录的是成功数而非总影响数

**文件**: [collection_service.py:126](file:///d:/Project/MarketLens/backend/services/collection_service.py#L126)

```python
self._write_run_log(conn, "quote", status, started_at, finished_at, error_message, success)
```

`affected_assets` 字段语义应为"受影响的标的数"，但这里只记录了成功数。失败数信息在 `error_message` 中，但 `affected_assets` 不包含失败数。

**建议**: 改为 `affected_assets=total`（总标的数），或增加 `failed_assets` 字段。

---

### M-4: `news_service.collect_news` 中每条新闻使用独立数据库连接

**文件**: [news_service.py:44-106](file:///d:/Project/MarketLens/backend/services/news_service.py#L44-L106)

去重检查和入库操作各自使用 `with get_db() as conn`，导致每条新闻需要 2-3 次连接获取/释放。在大量新闻场景下性能较差。

**建议**: 将整个循环放在同一个 `with get_db() as conn` 上下文中。

---

### M-5: `EvidenceBuilder._collect_data_sources` 重复查询数据库

**文件**: [evidence_builder.py:165-230](file:///d:/Project/MarketLens/backend/services/evidence_builder.py#L165-L230)

`_collect_data_sources` 方法对每种数据类型再次查询数据库获取 `source` 和 `collected_at`，但这些信息在 `_build_*` 方法中已经查询过。6 次额外查询浪费性能。

**建议**: 让 `_build_*` 方法在返回数据时附带 `source` 和 `collected_at` 信息，避免重复查询。

---

### M-6: `AIAnalyzer._check_fund_flow` 连续流入/流出判断逻辑有误

**文件**: [ai_analyzer.py:162-181](file:///d:/Project/MarketLens/backend/services/ai_analyzer.py#L162-L181)

当前逻辑遍历所有资金流记录，累计连续流入/流出次数，但只要中间出现一个零值就重置。实际上应该从最近一天开始往前数连续天数。当前逻辑统计的是"历史最长连续天数"而非"最近连续天数"。

**建议**: 从列表开头（最近日期）开始计数，遇到非同向即停止。

---

## [MINOR] 可维护性问题

### m-1: API 层服务实例在模块加载时创建

**文件**: [assets.py:10](file:///d:/Project/MarketLens/backend/api/assets.py#L10), [data.py:9](file:///d:/Project/MarketLens/backend/api/data.py#L9), [news.py:9](file:///d:/Project/MarketLens/backend/api/news.py#L9), [reports.py:10](file:///d:/Project/MarketLens/backend/api/reports.py#L10), [portfolio.py:8](file:///d:/Project/MarketLens/backend/api/portfolio.py#L8)

```python
_service = AssetService()
```

所有 API 路由模块在模块加载时创建服务实例，这意味着：
1. 应用启动时就会触发 Provider 初始化和 config 加载
2. 测试时无法轻松替换服务实例
3. 每个路由模块创建独立的服务实例，Provider 也被重复创建

**建议**: 使用 FastAPI 依赖注入（`Depends`）管理服务生命周期，或使用 `functools.lru_cache` 确保单例。

---

### m-2: 错误响应格式不一致

**文件**: 多个 API 文件

HTTPException 的 `detail` 字段有时是 `dict`（如 `{"error": "...", "detail": "..."}`），有时是 `str`。FastAPI 默认会将 `detail` 序列化为 JSON，当 `detail` 是 dict 时，最终响应体为 `{"detail": {"error": "...", "detail": "..."}}`，与 AGENTS.md 要求的 `{"error": "...", "detail": "..."}` 格式不一致。

**建议**: 自定义异常处理器，确保所有错误响应统一为 `{"error": "...", "detail": "..."}` 格式。

---

### m-3: `collection_service.py` 中 `collect_quotes` 和 `collect_quote_single` 存在大量重复代码

**文件**: [collection_service.py:62-128](file:///d:/Project/MarketLens/backend/services/collection_service.py#L62-L128) 和 [collection_service.py:130-173](file:///d:/Project/MarketLens/backend/services/collection_service.py#L130-L173)

两个方法的 Provider 遍历和行情入库逻辑几乎完全相同。

**建议**: 提取公共方法 `_collect_quote_for_symbol(conn, symbol)` 供两者复用。

---

### m-4: `portfolio_service.py` 中 `get_positions` 和 `_compute_avg_cost` 存在重复的均价计算逻辑

**文件**: [portfolio_service.py:326-422](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L326-L422) 和 [portfolio_service.py:484-510](file:///d:/Project/MarketLens/backend/services/portfolio_service.py#L484-L510)

均价计算逻辑在 `get_positions` 和 `_compute_avg_cost` 中重复实现。

**建议**: 提取为独立的 `_compute_position_detail(transactions)` 方法。

---

### m-5: `config.yaml` 中调度频率硬编码在 `TASK_SCHEDULE_DESCRIPTIONS` 中

**文件**: [jobs.py:21-26](file:///d:/Project/MarketLens/backend/scheduler/jobs.py#L21-L26)

```python
TASK_SCHEDULE_DESCRIPTIONS: dict[str, str] = {
    "quote": "每 15 分钟",
    "daily_close": "交易日 16:00",
    ...
}
```

调度描述硬编码了频率值，与 `config.yaml` 中的实际配置可能不一致。

**建议**: 从 `config.yaml` 动态生成调度描述。

---

### m-6: `ui/api_client.py` 中 `check_health` 在每次页面交互时调用

**文件**: [app.py:24-27](file:///d:/Project/MarketLens/ui/app.py#L24-L27)

```python
if check_health():
    st.success("API 已连接")
else:
    st.error("API 连接失败")
```

每次 Streamlit 重新渲染都会调用 `check_health()`，导致频繁的 HTTP 请求。

**建议**: 使用 `st.session_state` 缓存健康检查结果，设置 TTL（如 30 秒）。

---

## [NIT] 风格问题

### n-1: 部分文件使用 `Optional[str]` 而非 `str | None`

**文件**: [assets.py:1](file:///d:/Project/MarketLens/backend/api/assets.py#L1), [reports.py:1](file:///d:/Project/MarketLens/backend/api/reports.py#L1), [news.py:1](file:///d:/Project/MarketLens/backend/api/news.py#L1)

Python 3.13 已支持 `X | None` 语法，部分文件混用 `Optional[X]` 和 `X | None`。

**建议**: 统一使用 `X | None` 语法。

---

### n-2: `portfolio.py` 中 Pydantic 模型混用 `str | None` 和 `Optional[str]`

**文件**: [portfolio.py](file:///d:/Project/MarketLens/backend/api/portfolio.py)

同一文件中 `CreateAccountRequest` 使用 `str | None`，而 `UpdateAccountRequest` 也使用 `str | None`，但其他 API 文件使用 `Optional[str]`。

**建议**: 全项目统一类型注解风格。

---

## 审查总结

| 严重级别 | 数量 | 阻塞合并？ |
|----------|------|-----------|
| CRITICAL | 3 | 是 |
| MAJOR | 6 | 是 |
| MINOR | 6 | 否 |
| NIT | 2 | 否 |

### 优先修复建议

1. **C-1/C-2**: LIKE 通配符转义 — 影响数据查询准确性
2. **C-3**: symbol 匹配精度 — 影响新闻关联准确性
3. **M-1**: 持仓计算排序 — 影响盈亏计算正确性
4. **M-4**: 新闻采集性能 — 大量新闻时性能瓶颈
5. **M-6**: 资金流连续判断 — 影响 AI 分析准确性
6. **m-2**: 错误响应格式 — 影响 API 一致性
