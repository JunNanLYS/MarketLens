# 标的管理 API

> 基准路径: `/api/v1/assets` | 返回上级: [API 概述](/docs/api.md)

---

## 鉴权

| 方法 | 是否需要 API Key |
|---|---|
| `GET` | 否 |
| `POST` | 是（需 `X-API-Key` 头） |
| `PATCH` | 是（需 `X-API-Key` 头） |
| `DELETE` | 是（需 `X-API-Key` 头） |

API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。详见 `docs/api.md` 鉴权章节。

---

## 接口清单

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/assets` | 追踪列表（分页/筛选） | 200 |
| `POST` | `/assets` | 添加标的 | 201, 400, 401, 409 |
| `GET` | `/assets/search` | 搜索外部标的 | 200, 422 |
| `GET` | `/assets/{id}` | 标的详情（聚合行情等） | 200, 404 |
| `PATCH` | `/assets/{id}` | 部分更新（启用/标签/备注） | 200, 401, 404, 422 |
| `DELETE` | `/assets/{id}` | 删除标的 | 204, 401, 404 |

---

## `GET /assets` — 追踪列表

查询 `enabled` / `market` / `asset_type` / `tag` / `page` / `page_size`。

```http
GET /api/v1/assets?market=hk&enabled=true&page=1&page_size=10 HTTP/1.1
```

<details>
<summary>响应示例</summary>

```json
{
  "items": [
    {
      "id": 1,
      "symbol": "hk00700",
      "name": "腾讯控股",
      "market": "hk",
      "asset_type": "stock",
      "enabled": true,
      "tags": ["互联网", "港股通"],
      "notes": "长期关注",
      "latest_price": 385.0,
      "latest_change_pct": 1.2,
      "latest_quote_at": "2026-05-31T15:30:00+08:00",
      "created_at": "2026-05-20T10:00:00+08:00",
      "updated_at": "2026-05-31T15:30:00+08:00"
    }
  ],
  "page_info": { "page": 1, "page_size": 10, "total": 1, "total_pages": 1 }
}
```
</details>

---

## `POST /assets` — 添加标的

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | string | 是 | 代码（含市场前缀），如 `hk00700` |
| `name` | string | 否 | 名称，留空自动补全 |
| `market` | string | 否 | 市场，留空从代码前缀推断 |
| `asset_type` | string | 否 | 类型：`stock` / `etf` / `index` / `future`，默认 `stock` |
| `tags` | string[] | 否 | 标签列表 |
| `notes` | string | 否 | 备注 |

```http
POST /api/v1/assets HTTP/1.1
Content-Type: application/json

{ "symbol": "hk00700", "asset_type": "stock", "tags": ["互联网"] }
```

<details>
<summary>成功 201</summary>

```http
HTTP/1.1 201 Created
Location: /api/v1/assets/1

{
  "id": 1, "symbol": "hk00700", "name": "腾讯控股", "market": "hk",
  "asset_type": "stock", "enabled": true,
  "tags": ["互联网"], "notes": null,
  "created_at": "2026-05-31T10:00:00+08:00",
  "updated_at": "2026-05-31T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 400 — 无效代码</summary>

```json
{ "error": "INVALID_SYMBOL", "message": "无法识别代码 'xyz999'" }
```
</details>

<details>
<summary>错误 409 — 重复</summary>

返回结构携带 `existing_asset` 快照，前端据此判断是「已启用」还是「已停用」：

```json
{
  "detail": {
    "error": "ASSET_EXISTS",
    "message": "标的 'hk00700' 已在追踪列表中（ID: 1，已停用）",
    "existing_asset": {
      "id": 1,
      "symbol": "hk00700",
      "name": "腾讯控股",
      "market": "hk",
      "asset_type": "stock",
      "enabled": false
    }
  }
}
```

`existing_asset.enabled` 语义：
- `true`  —— 标的已启用，前端应提示「已在追踪列表」。
- `false` —— 标的已被软删除（停用），前端应提示「已停用」并提供一键启用入口。
</details>

---

## `GET /assets/search` — 搜索外部标的

```http
GET /api/v1/assets/search?keyword=腾讯&market=hk HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    { "symbol": "hk00700", "name": "腾讯控股", "market": "hk",
      "asset_type": "stock", "latest_price": 385.0, "source": "westock" }
  ],
  "total": 1
}
```
</details>

---

## `GET /assets/{id}` — 标的详情（聚合）

返回标的基本信息 + `quote` + `kline_summary` + `finance_summary` + `fund_flow_summary` + `latest_report`。

```http
GET /api/v1/assets/1 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "id": 1, "symbol": "hk00700", "name": "腾讯控股",
  "market": "hk", "asset_type": "stock", "enabled": true,
  "tags": ["互联网"], "notes": "长期关注",
  "quote": {
    "price": 385.0, "change": 4.6, "change_pct": 1.2,
    "open": 382.0, "high": 387.5, "low": 381.0,
    "prev_close": 380.4, "volume": 23456789, "amount": 9034567890,
    "collected_at": "2026-05-31T15:30:00+08:00"
  },
  "kline_summary": {
    "latest_close": 385.0, "ma5": 382.5, "ma20": 378.0, "ma60": 370.0,
    "trend": "MA5 > MA20 > MA60 多头排列"
  },
  "finance_summary": {
    "report_period": "2026Q1", "revenue_yoy": 8.5, "eps": 12.8, "roe": 18.2
  },
  "fund_flow_summary": {
    "net_flow_5d": 520000000, "trend": "连续 3 日净流入"
  },
  "latest_report": {
    "symbol": "sh600519", "name": "贵州茅台",
    "action": "watch", "confidence": 0.52,
    "risk_level": "low",
    "summary": "...",
    "bullish_reasons": ["ROE=20.5% 且营收正增长"],
    "bearish_reasons": [],
    "key_risks": [],
    "data_used": [{"type": "quote", "source": "sina", "collected_at": "..."}],
    "generated_at": "2026-05-31T20:00:00+08:00"
  }
}
```
</details>

---

## `PATCH /assets/{id}` — 部分更新

可更新字段：`enabled`、`tags`（全量替换）、`notes`。

```http
PATCH /api/v1/assets/1 HTTP/1.1
Content-Type: application/json

{ "tags": ["互联网", "AI概念"], "notes": "增加标签" }
```

---

## `DELETE /assets/{id}` — 删除标的

`?soft=true`（默认）仅停用标记；`?soft=false` 物理删除。关联历史数据不级联删除。

```http
DELETE /api/v1/assets/1 HTTP/1.1
```

→ `204 No Content`
