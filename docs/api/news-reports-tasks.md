# 新闻 + AI 报告 + 任务管理 API

## 新闻

> 基准路径: `/api/v1/news` | 返回上级: [API 概述](/docs/api.md)

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/news` | 新闻列表 | 200 |
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
| `GET` | `/reports` | 报告列表 | 200 |
| `GET` | `/reports/{symbol}` | 指定标的最新报告 | 200, 404 |
| `GET` | `/reports/{symbol}/history` | 指定标的历史报告 | 200, 404 |
| `POST` | `/reports/generate` | 手动生成报告 | 200, 400 |

### `GET /reports` — 报告列表

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `action` | string | — | `buy` / `sell` / `watch` / `avoid` |
| `risk_level` | string | — | `low` / `medium` / `high` |
| `date` | date | 今天 | 日期筛选 |
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
| `from` / `to` | date | — | 日期范围 |

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
| `GET` | `/tasks/status` | 任务运行状态 | 200 |
| `POST` | `/tasks/trigger/{name}` | 手动触发 | 202, 400, 404 |
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

`name` 可选：`quote` / `daily_close` / `news` / `ai_report`

```http
POST /api/v1/tasks/trigger/quote HTTP/1.1
```

→ `202 Accepted`：`{ "task_name": "quote", "status": "triggered" }`

### `GET /tasks/logs` — 运行日志

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `task_name` | string | — | 筛选任务 |
| `status` | string | — | `success`：成功完成；`failure`：异常终止 |
| `days` | integer | 7 | 最近 N 天 |
| `page` / `page_size` | int | 1 / 20 | 分页 |

```http
GET /api/v1/tasks/logs?task_name=quote&status=success&days=7 HTTP/1.1
```

> 注：`run_logs.status` 字段当前仅持久化 `success` / `failure` 两种终态（写入端在 `collection_service.py:132/172`、`news_service.py:133`、`report_service.py:54`）。UI 的「running」选项在当前数据库 schema 下不会命中任何记录。
