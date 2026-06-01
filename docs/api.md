# MarketLens API 文档

> 版本: v1 | 基准路径: `http://localhost:8000/api/v1` | 协议: HTTP | 内容类型: `application/json; charset=utf-8`

---

## 快速导航

| 资源组 | 文档 | 接口数 |
|---|---|---|
| 🏷️ 标的管理 | [assets](api/assets.md) | 6 |
| 📊 市场数据 | [data](api/data.md) | 6 |
| 📰 新闻 | [news / reports / tasks](api/news-reports-tasks.md#新闻) | 2 |
| 🧠 AI 报告 | [news / reports / tasks](api/news-reports-tasks.md#ai-报告) | 4 |
| ⏰ 任务管理 | [news / reports / tasks](api/news-reports-tasks.md#任务管理) | 3 |
| 🔑 NeoData Token | [neodata](api/neodata.md) | 2 |
| 💼 投资组合 | [portfolio](api/portfolio.md) | 12 |

---

## 一页速览（35 个接口）

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/assets` | 追踪列表 |
| `POST` | `/assets` | 添加标的 |
| `POST` | `/assets/search` | 搜索外部标的 |
| `GET` | `/assets/{id}` | 标的详情（聚合） |
| `PATCH` | `/assets/{id}` | 部分更新 |
| `DELETE` | `/assets/{id}` | 删除 |
| `GET` | `/data/quotes/{symbol}` | 最新行情 |
| `GET` | `/data/quotes/{symbol}/history` | 历史行情 |
| `GET` | `/data/kline/{symbol}` | 日 K 线 |
| `GET` | `/data/finance/{symbol}` | 财务数据 |
| `GET` | `/data/fund-flow/{symbol}` | 资金流向 |
| `GET` | `/data/technical/{symbol}` | 技术指标 |
| `GET` | `/news` | 新闻列表 |
| `GET` | `/news/{id}` | 新闻详情 |
| `GET` | `/reports` | 报告列表 |
| `GET` | `/reports/{symbol}` | 标的最新报告 |
| `GET` | `/reports/{symbol}/history` | 历史报告 |
| `POST` | `/reports/generate` | 手动生成报告 |
| `GET` | `/tasks/status` | 任务状态 |
| `POST` | `/tasks/trigger/{name}` | 手动触发 |
| `GET` | `/tasks/logs` | 运行日志 |
| `POST` | `/accounts` | 创建账户 |
| `GET` | `/accounts` | 账户列表 |
| `GET` | `/accounts/{account_id}` | 账户详情 |
| `PATCH` | `/accounts/{account_id}` | 更新账户 |
| `DELETE` | `/accounts/{account_id}` | 删除账户 |
| `POST` | `/transactions` | 录入交易 |
| `GET` | `/transactions` | 交易历史 |
| `GET` | `/transactions/{transaction_id}` | 交易详情 |
| `PATCH` | `/transactions/{transaction_id}` | 更新交易 |
| `DELETE` | `/transactions/{transaction_id}` | 删除交易 |
| `GET` | `/positions` | 持仓总览 |
| `GET` | `/positions/realized-pnl` | 已实现盈亏 |

---

## 通用约定

| GET | /neodata/token-status | Token 状态 |
| POST | /neodata/token | 保存 Token |

### 分页

所有列表接口统一使用页码分页：

```
?page=1&page_size=20
```

响应包裹：

```json
{ "items": [...], "page_info": { "page": 1, "page_size": 20, "total": 156, "total_pages": 8 } }
```

### 错误响应

```json
{ "error": "ERROR_CODE", "detail": "人类可读的描述" }
```

### 时间格式

ISO 8601 带时区：`"2026-05-31T15:30:00+08:00"`

### 数据溯源

所有数据响应均含 `source`（数据源）和 `collected_at`（采集时间）字段。

> MVP 阶段无认证要求（本地单用户）。

---

## 错误码速查

| 状态码 | 错误码 | 场景 |
|---|---|---|
| `400` | `INVALID_SYMBOL` | 代码格式错误 |
| `400` | `MALFORMED_JSON` | JSON 解析失败 |
| `400` | `SEARCH_FAILED` | 外部搜索全部失败 |
| `404` | `ASSET_NOT_FOUND` | 标的 ID 不存在 |
| `404` | `SYMBOL_NOT_FOUND` | 标的代码无数据 |
| `404` | `REPORT_NOT_FOUND` | 无报告 |
| `404` | `TASK_NOT_FOUND` | 任务名不存在 |
| `409` | `ASSET_EXISTS` | 标的重复 |
| `409` | `ACCOUNT_EXISTS` | 账户名称重复 |
| `404` | `ACCOUNT_NOT_FOUND` | 账户不存在 |
| `400` | `INSUFFICIENT_HOLDING` | 卖出超过持仓 |
| `404` | `TRANSACTION_NOT_FOUND` | 交易不存在 |
| `422` | `VALIDATION_FAILED` | 字段校验失败 |
| `500` | `INTERNAL_ERROR` | 服务端异常 |
| `503` | `DATA_SOURCE_UNAVAILABLE` | 所有数据源不可用 |

---

## 枚举值

| 枚举 | 可选值 |
|---|---|
| `market` | `sh` / `sz` / `hk` / `us` |
| `asset_type` | `stock` / `etf` / `index` / `future`（MVP）；`forex` / `commodity`（预留） |
| `action` | `buy` / `sell` / `watch` / `avoid` |
| `risk_level` | `low` / `medium` / `high` |
| `sentiment` | `positive` / `negative` / `neutral` |
| `source` | `westock` / `sina` / `sina_rss` / `neodata` |
| `task_name` | `quote` / `daily_close` / `news` / `ai_report` |
| `transaction_type` | `buy` / `sell` / `dividend` / `split` |

---

## RESTful 设计原则

| # | 原则 | 体现 |
|---|---|---|
| 1 | 名词复数资源 | `/assets` 而非 `/getAssets` |
| 2 | 方法语义正确 | `GET` 只读，`POST` 创建，`PATCH` 更新，`DELETE` 删除 |
| 3 | 避免路径动词 | `POST /assets/search` 作为搜索资源操作 |
| 4 | 动作名词化 | `POST /reports/generate` 建模为生成资源 |
| 5 | 层级 ≤ 2 层 | `/assets/{id}`、`/reports/{symbol}/history` |
| 6 | 版本化 | `/api/v1/` 路径前缀，开放演进 |

