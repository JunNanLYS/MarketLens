# 新闻 + AI 报告 + 任务管理 API

## 鉴权

| 模块 | 需要 API Key 的端点 |
|---|---|
| 新闻 | 无（全部 GET） |
| AI 报告 | `POST /reports/generate` |
| 任务管理 | `POST /tasks/trigger/{name}` |

`GET` 端点公开访问。API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。

---

## 新闻

> 基准路径: `/api/v1/news` | 返回上级: [API 概述](/docs/api.md)

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/news` | 新闻列表 | 200, 422 |
| `GET` | `/news/{id}` | 新闻详情 | 200, 404 |

### `GET /news` — 新闻列表

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `symbol` | string | — | 关联标的代码 |
| `days` | integer | 7 | 最近 N 天 |
| `sentiment` | string | — | `positive` / `negative` / `neutral` |
| `source` | string | — | `sina_rss` / `neodata` |
| `page` / `page_size` | int | 1 / 20 | 分页 |

```http
GET /api/v1/news?symbol=hk00700&days=7 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    {
      "id": 1,
      "title": "腾讯控股 Q1 财报超预期，营收同比增长 8.5%",
      "source": "sina_rss",
      "url": "https://finance.sina.com.cn/...",
      "published_at": "2026-05-31T14:30:00+08:00",
      "summary": "腾讯控股发布 2026 年第一季度财报...",
      "sentiment": "positive", "importance": "high",
      "confidence": 0.85, "sentiment_reason": "央行降息刺激市场情绪", "sectors": ["银行", "地产"],
      "related_symbols": ["hk00700"],
      "collected_at": "2026-05-31T15:00:00+08:00"
    }
  ],
  "page_info": { "page": 1, "page_size": 20, "total": 8, "total_pages": 1 }
}
```
</details>

### `GET /news/{id}` — 新闻详情

```http
GET /api/v1/news/1 HTTP/1.1
```

返回完整 `content` 字段（含正文）。

---

## AI 报告

> 基准路径: `/api/v1/reports` | 返回上级: [API 概述](/docs/api.md)

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/reports` | 报告列表 | 200, 422 |
| `GET` | `/reports/{symbol}` | 指定标的最新报告 | 200, 404 |
| `GET` | `/reports/{symbol}/history` | 指定标的历史报告 | 200, 422 |
| `POST` | `/reports/generate` | 手动生成报告 | 200, 400, 401 |

### `GET /reports` — 报告列表

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `action` | string | — | `buy` / `sell` / `watch` / `avoid` |
| `risk_level` | string | — | `low` / `medium` / `high` |
| `date` | date | — | 日期筛选（ISO 8601 `YYYY-MM-DD`），匹配 `date(generated_at)`；非法格式返回 422 |
| `page` / `page_size` | int | 1 / 20 | 分页 |

```http
GET /api/v1/reports?date=2026-05-31 HTTP/1.1
```

### `GET /reports/{symbol}` — 指定标的最新报告

```http
GET /api/v1/reports/hk00700 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "id": 1, "symbol": "hk00700", "name": "腾讯控股",
  "action": "watch", "confidence": 0.52, "risk_level": "medium",
  "summary": "短期趋势震荡，新闻偏正面，资金面尚未确认。",
  "bullish_reasons": ["营收同比增长 8.5%", "近 3 日新闻正面占比 62%"],
  "bearish_reasons": ["MACD 高位存在死叉风险", "ROE 小幅下滑"],
  "key_risks": ["财报季业绩不确定性", "监管政策变化风险"],
  "data_used": [
    { "source": "westock", "type": "kline_daily",
      "collected_at": "2026-05-31T16:05:00+08:00" },
    { "source": "westock", "type": "fund_flow",
      "collected_at": "2026-05-31T16:05:00+08:00" },
    { "source": "sina_rss", "type": "news",
      "collected_at": "2026-05-31T15:00:00+08:00" }
  ],
  "generated_at": "2026-05-31T20:00:00+08:00"
}
```
</details>

### `GET /reports/{symbol}/history` — 历史报告

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 30 | 最大 90 |
| `from` / `to` | date | — | 日期范围，ISO 8601 `YYYY-MM-DD`；非法格式返回 422 |

### `POST /reports/generate` — 手动生成

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `symbols` | string[] | 否 | 标的列表，空=全部启用标的 |
| `force` | boolean | 否 | 是否覆盖当日已有报告 |

```http
POST /api/v1/reports/generate HTTP/1.1
Content-Type: application/json

{ "symbols": ["hk00700", "sh600519"], "force": false }
```

→ `200 OK`：`{ "status": "completed", "generated": 2, "skipped": 0 }`

> `status: "completed"` 表示同步执行已结束；`generated` 是实际生成数，`skipped` 是因已存在当日报告而跳过的数。UI 据此显示成功提示。

---

## 任务管理

> 基准路径: `/api/v1/tasks` | 返回上级: [API 概述](/docs/api.md)

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/tasks/status` | 任务运行状态 | 200, 503 |
| `POST` | `/tasks/trigger/{name}` | 手动触发 | 202, 401, 404, 500, 503 |
| `GET` | `/tasks/logs` | 运行日志 | 200 |

### `GET /tasks/status`

```http
GET /api/v1/tasks/status HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    {
      "task_name": "quote", "description": "实时行情采集",
      "schedule": "每 15 分钟",
      "last_run_at": "2026-05-31T15:30:00+08:00",
      "last_status": "success", "last_duration_ms": 2340,
      "last_affected_assets": 20, "last_error": null,
      "next_run_at": "2026-05-31T15:45:00+08:00"
    },
    {
      "task_name": "ai_report", "description": "AI 分析报告",
      "schedule": "每日 20:00",
      "last_run_at": "2026-05-30T20:00:00+08:00",
      "last_status": "success", "last_duration_ms": 45000,
      "last_affected_assets": 20, "last_error": null,
      "next_run_at": "2026-05-31T20:00:00+08:00"
    }
  ]
}
```
</details>

### `POST /tasks/trigger/{name}` — 手动触发

`name` 可选：`quote` / `daily_close` / `news` / `ai_report` / `cleanup`

```http
POST /api/v1/tasks/trigger/quote HTTP/1.1
```

→ `202 Accepted`：`{ "task_name": "quote", "status": "triggered" }`

### `GET /tasks/logs` — 运行日志

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `task_name` | string | — | 筛选任务 |
| `status` | string | — | `success` / `failed` / `running`（与 `run_logs.status` 字段对齐） |
| `page` | int | 1 | 页码（≥ 1） |
| `page_size` | int | 20 | 每页条数（1-100） |

```http
GET /api/v1/tasks/logs?task_name=quote&status=success HTTP/1.1
```

> 注：`run_logs.status` 字段当前 schema 允许 `success` / `failed` / `running` 三种值（见 `docs/api.md` 枚举值表），但写入端在 `collection_service.py` / `news_service.py` / `report_service.py` 中只持久化 `success` / `failed` 终态；UI 的「running」选项在当前实现下不会命中任何记录（与 `docs/api.md` 中 `status` 枚举保持一致）。
