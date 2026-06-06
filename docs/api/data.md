# 市场数据 API

> 基准路径: `/api/v1/data` | 返回上级: [API 概述](/docs/api.md)

---

## 鉴权

| 方法 | 是否需要 API Key |
|---|---|
| `GET` | 否 |
| `POST` | 是（需 `X-API-Key` 头） |

API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。所有 POST 端点（`/quotes/{symbol}/refresh`、`/intraday/{symbol}`、`/shareholder/{symbol}`、`/dividend/{symbol}`、`/reserve/{symbol}`、`/dividend/{symbol}/refresh`、`/shareholder/{symbol}/refresh`、`/reserve/{symbol}/refresh`、`/minute/{symbol}/refresh`、`/etf-refresh/{symbol}`、`/sectors/refresh`、`/finance-refresh/{symbol}`、`/calendar-refresh`、`/chip-refresh/{symbol}`、`/blocktrade-refresh/{symbol}`、`/lhb-refresh/{symbol}`）均受保护。

---

## 接口清单

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/data/quotes/{symbol}` | 最新行情 | 200, 404 |
| `POST` | `/data/quotes/{symbol}/refresh` | 手动刷新行情 | 200, 401, 502 |
| `GET` | `/data/quotes/{symbol}/history` | 历史行情序列 | 200, 404, 422 |
| `GET` | `/data/kline/{symbol}` | 日 K 线 | 200, 404, 422 |
| `GET` | `/data/finance/{symbol}` | 财务数据 | 200, 404, 422 |
| `GET` | `/data/fund-flow/{symbol}` | 资金流向 | 200, 404, 422 |
| `GET` | `/data/technical/{symbol}` | 技术指标 | 200, 404 |
| `POST` | `/data/intraday/{symbol}` | 分时数据采集 | 200, 401, 422, 502 |
| `POST` | `/data/shareholder/{symbol}` | 股东结构采集 | 200, 401, 502 |
| `POST` | `/data/dividend/{symbol}` | 分红数据采集 | 200, 401, 502 |
| `POST` | `/data/reserve/{symbol}` | 业绩预告采集 | 200, 401, 502 |
| `GET` | `/data/dividend/{symbol}` | 分红记录（落库） | 200, 404, 422 |
| `GET` | `/data/shareholder/{symbol}` | 股东结构（落库） | 200, 404, 422 |
| `GET` | `/data/reserve/{symbol}` | 业绩预告（落库） | 200, 404, 422 |
| `GET` | `/data/minute/{symbol}` | 分时 K 线（落库） | 200, 404, 422 |
| `POST` | `/data/dividend/{symbol}/refresh` | 刷新分红 | 200, 401, 502 |
| `POST` | `/data/shareholder/{symbol}/refresh` | 刷新股东结构 | 200, 401, 502 |
| `POST` | `/data/reserve/{symbol}/refresh` | 刷新业绩预告 | 200, 401, 502 |
| `POST` | `/data/minute/{symbol}/refresh` | 刷新分时 | 200, 401, 422, 502 |
| `GET` | `/data/etf/{symbol}` | ETF 基本信息 | 200, 404 |
| `GET` | `/data/etf/{symbol}/holdings` | ETF 成分股 | 200, 404, 422 |
| `GET` | `/data/etf/{symbol}/nav` | ETF 历史净值 | 200, 404, 422 |
| `GET` | `/data/etf/{symbol}/holders` | ETF 持有人结构 | 200, 404 |
| `GET` | `/data/etf/{symbol}/financial` | ETF 资产配置 | 200, 404 |
| `POST` | `/data/etf-refresh/{symbol}` | 刷新 ETF 全套 | 200, 401, 422 |
| `GET` | `/data/sectors/board` | 板块首页（行业/概念涨幅榜） | 200, 404, 422 |
| `GET` | `/data/sectors/hot` | 热门板块 | 200, 404, 422 |
| `POST` | `/data/sectors/refresh` | 刷新板块首页 + 热门 | 200, 401, 422 |
| `GET` | `/data/finance/us/{symbol}` | 美股财务 | 200, 404, 422 |
| `GET` | `/data/finance/hk/{symbol}` | 港股财务 | 200, 404, 422 |
| `POST` | `/data/finance-refresh/{symbol}` | 刷新港美股财务 | 200, 400, 401, 422 |
| `GET` | `/data/calendar/ipo` | 新股日历 | 200, 404, 422 |
| `GET` | `/data/calendar/exdiv/{symbol}` | 除权日历 | 200, 404 |
| `POST` | `/data/calendar-refresh` | 刷新新股/除权日历 | 200, 401, 422 |
| `GET` | `/data/chip/{symbol}` | 筹码成本 | 200, 404, 422 |
| `GET` | `/data/margintrade/{symbol}` | 融资融券 | 200, 404, 422 |
| `GET` | `/data/blocktrade/{symbol}` | 大宗交易 | 200, 404, 422 |
| `GET` | `/data/lhb/{symbol}` | 龙虎榜 | 200, 404, 422 |
| `POST` | `/data/chip-refresh/{symbol}` | 刷新筹码+融资融券 | 200, 401 |
| `POST` | `/data/blocktrade-refresh/{symbol}` | 刷新大宗交易 | 200, 401, 422, 502 |
| `POST` | `/data/lhb-refresh/{symbol}` | 刷新龙虎榜 | 200, 401, 422, 502 |

> 所有数据均包含 `source` 和 `collected_at` 字段以支持追溯。

---

## `GET /data/quotes/{symbol}` — 最新行情

```http
GET /api/v1/data/quotes/hk00700 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "price": 385.0, "change": 4.6, "change_pct": 1.2,
  "open": 382.0, "high": 387.5, "low": 381.0, "prev_close": 380.4,
  "volume": 23456789, "amount": 9034567890.0,
  "amplitude": 1.71, "turnover_rate": 0.25,
  "high_52w": 420.0, "low_52w": 310.0,
  "source": "westock",
  "collected_at": "2026-05-31T15:30:00+08:00"
}
```
</details>

---

## `POST /data/quotes/{symbol}/refresh` — 手动刷新行情

```http
POST /api/v1/data/quotes/hk00700/refresh HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "price": 385.0, "change": 4.6, "change_pct": 1.2,
  "open": 382.0, "high": 387.5, "low": 381.0, "prev_close": 380.4,
  "volume": 23456789, "amount": 9034567890.0,
  "source": "westock",
  "collected_at": "2026-06-04T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 502 — 数据源刷新失败</summary>

```json
{ "error": "REFRESH_FAILED", "detail": "标的 'hk00700' 数据刷新失败" }
```
</details>

---

## `GET /data/quotes/{symbol}/history` — 历史行情

| `limit` | integer | 100 | 最大 500 |

```http
GET /api/v1/data/quotes/hk00700/history?limit=24 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    { "price": 385.0, "change_pct": 1.2, "volume": 23456789,
      "collected_at": "2026-05-31T15:30:00+08:00" },
    { "price": 380.4, "change_pct": -0.5, "volume": 18901234,
      "collected_at": "2026-05-31T15:15:00+08:00" }
  ],
  "total": 24
}
```
</details>

---

## `GET /data/kline/{symbol}` — 日 K 线

| `to` | date | — | 结束日期 |

```http
GET /api/v1/data/kline/hk00700?limit=30 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "date": "2026-05-31", "open": 382.0, "high": 387.5,
      "low": 381.0, "close": 385.0, "volume": 23456789,
      "change_pct": 1.2, "source": "westock",
      "collected_at": "2026-05-31T16:05:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

---

## `GET /data/finance/{symbol}` — 财务数据

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 4 | 取值范围 1-20 |

```http
GET /api/v1/data/finance/hk00700 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "report_period": "2026Q1",
      "revenue": 159500000000.0, "revenue_yoy": 8.5,
      "net_profit": 41900000000.0, "net_profit_yoy": 12.3,
      "eps": 12.8, "roe": 18.2, "debt_ratio": 42.5,
      "gross_margin": 55.0, "net_margin": 26.3,
      "source": "westock",
      "collected_at": "2026-05-31T16:05:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

---

## `GET /data/fund-flow/{symbol}` — 资金流向

```http
GET /api/v1/data/fund-flow/hk00700?days=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "date": "2026-05-31",
      "main_net_inflow": 380000000,
      "super_large_net_inflow": 150000000, "large_net_inflow": 230000000,
      "medium_net_inflow": -50000000, "small_net_inflow": -120000000,
      "net_inflow_ratio": 4.2,
      "source": "westock",
      "collected_at": "2026-05-31T16:05:00+08:00"
    }
  ],
  "summary": {
    "net_flow_5d": 520000000, "trend": "连续 3 日净流入",
    "avg_net_inflow_ratio": 3.1
  }
}
```
</details>

---

## `GET /data/technical/{symbol}` — 技术指标

```http
GET /api/v1/data/technical/hk00700 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700", "date": "2026-05-31",
  "ma": { "ma5": 382.5, "ma10": 380.0, "ma20": 378.0, "ma60": 370.0 },
  "macd": { "dif": 2.8, "dea": 2.1, "histogram": 0.7 },
  "rsi": { "rsi6": 58.3, "rsi14": 54.7 },
  "boll": { "upper": 392.0, "middle": 378.0, "lower": 364.0, "position": "中轨上方" },
  "volume_ma": { "ma5": 21000000, "ma20": 19500000 },
  "source": "westock",
  "collected_at": "2026-05-31T16:05:00+08:00"
}
```
</details>

---

## `POST /data/intraday/{symbol}` — 分时数据

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `days` | integer | 1 | 取值范围 1-5 |

```http
POST /api/v1/data/intraday/hk00700?days=1 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "time": "09:30",
      "price": 380.0,
      "volume": 1234567,
      "avg_price": 380.0,
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ]
}
```
</details>

<details>
<summary>错误 502 — 数据源采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 'hk00700' 分时数据采集失败" }
```
</details>

> 分时数据实时采集，不落库缓存。

---

## `POST /data/shareholder/{symbol}` — 股东结构

```http
POST /api/v1/data/shareholder/sh600519 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "top_shareholders": [
    {
      "rank": 1,
      "name": "中国贵州茅台酒厂(集团)有限责任公司",
      "shares": 700000000,
      "ratio": 58.0,
      "change": null
    }
  ],
  "holder_count_history": [
    {
      "date": "2025-12-31",
      "total_holders": 150000,
      "avg_shares": 8000
    }
  ],
  "source": "westock",
  "collected_at": "2026-06-02T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 502 — 数据源采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 'sh600519' 股东结构数据采集失败" }
```
</details>

> 股东结构数据实时采集，不落库缓存。包含十大股东列表和股东人数变化历史。

---

## `POST /data/reserve/{symbol}` — 业绩预告

```http
POST /api/v1/data/reserve/sz000001 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sz000001",
  "report_period": "2025Q4",
  "forecast_type": "预增",
  "profit_lower": 500000000,
  "profit_upper": 550000000,
  "change_lower": 20.0,
  "change_upper": 32.0,
  "summary": "业绩大幅增长",
  "source": "westock",
  "collected_at": "2026-06-02T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 502 — 数据源采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 'sz000001' 业绩预告采集失败" }
```
</details>

> 业绩预告数据实时采集，返回最新一条预告。

---

## `POST /data/dividend/{symbol}` — 分红数据

```http
POST /api/v1/data/dividend/sh600519 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "report_period": "2025",
      "record_date": "2026-01-15",
      "ex_date": "2026-01-16",
      "pay_date": "2026-01-20",
      "dividend_per_share": 30.88,
      "bonus_shares": 0.0,
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 502 — 数据源采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 'sh600519' 分红数据采集失败" }
```
</details>

> 分红数据实时采集，按报告期倒序返回历史分红记录。

---

## `GET /data/dividend/{symbol}` — 分红记录（落库）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |
| `source` | string | — | 可选，按数据源过滤 |

```http
GET /api/v1/data/dividend/sh600519?limit=10 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "ex_date": "2026-01-16",
      "cash_dividend": 30.88,
      "share_bonus": 0.0,
      "record_date": "2026-01-15",
      "announce_date": "2025-12-20",
      "dividend_year": 2025,
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "标的 sh600519 无分红数据" }
```
</details>

---

## `GET /data/shareholder/{symbol}` — 股东结构（落库）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 10 | top_shareholders 返回行数上限，取值 1-100 |
| `source` | string | — | 可选，按数据源过滤 |

```http
GET /api/v1/data/shareholder/sh600519 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "top_shareholders": [
    {
      "id": 1,
      "symbol": "sh600519",
      "report_period": "2025Q4",
      "rank": 1,
      "name": "中国贵州茅台酒厂(集团)有限责任公司",
      "shares": 700000000,
      "ratio": 58.0,
      "change_amount": 0.0,
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ],
  "holder_count_history": [
    {
      "id": 1,
      "symbol": "sh600519",
      "report_date": "2025-12-31",
      "total_holders": 150000,
      "avg_shares": 8000,
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ]
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "标的 sh600519 无股东数据" }
```
</details>

---

## `GET /data/reserve/{symbol}` — 业绩预告（落库）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |
| `source` | string | — | 可选，按数据源过滤 |

```http
GET /api/v1/data/reserve/sz000001?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sz000001",
  "items": [
    {
      "id": 1,
      "symbol": "sz000001",
      "report_period": "2025Q4",
      "forecast_type": "预增",
      "profit_lower": 500000000,
      "profit_upper": 550000000,
      "change_lower": 20.0,
      "change_upper": 32.0,
      "summary": "业绩大幅增长",
      "source": "westock",
      "collected_at": "2026-06-02T10:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "标的 sz000001 无业绩预告数据" }
```
</details>

---

## `GET /data/minute/{symbol}` — 分时 K 线（落库）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `from` | datetime | — | 起始时间（ISO 字符串） |
| `to` | datetime | — | 截止时间（ISO 字符串） |
| `limit` | integer | 240 | 取值范围 1-1440（默认 240 对应 4 小时 1 分钟 K） |

```http
GET /api/v1/data/minute/hk00700?limit=120 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "id": 1,
      "symbol": "hk00700",
      "time": "2026-06-02T10:00:00+08:00",
      "price": 380.0,
      "volume": 1234567,
      "avg_price": 380.0,
      "source": "westock",
      "collected_at": "2026-06-02T10:30:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "标的 hk00700 无分时数据" }
```
</details>

---

## `POST /data/dividend/{symbol}/refresh` — 刷新分红

```http
POST /api/v1/data/dividend/sh600519/refresh HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "ex_date": "2026-01-16",
      "cash_dividend": 30.88,
      "share_bonus": 0.0,
      "source": "westock",
      "collected_at": "2026-06-04T10:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 sh600519 分红数据采集失败" }
```
</details>

---

## `POST /data/shareholder/{symbol}/refresh` — 刷新股东结构

```http
POST /api/v1/data/shareholder/sh600519/refresh HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "top_shareholders": [
    { "rank": 1, "name": "中国贵州茅台酒厂(集团)有限责任公司", "shares": 700000000, "ratio": 58.0 }
  ],
  "holder_count_history": [
    { "report_date": "2025-12-31", "total_holders": 150000, "avg_shares": 8000 }
  ],
  "source": "westock",
  "collected_at": "2026-06-04T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 sh600519 股东结构数据采集失败" }
```
</details>

---

## `POST /data/reserve/{symbol}/refresh` — 刷新业绩预告

```http
POST /api/v1/data/reserve/sz000001/refresh HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sz000001",
  "report_period": "2025Q4",
  "forecast_type": "预增",
  "profit_lower": 500000000,
  "profit_upper": 550000000,
  "change_lower": 20.0,
  "change_upper": 32.0,
  "summary": "业绩大幅增长",
  "source": "westock",
  "collected_at": "2026-06-04T10:00:00+08:00"
}
```
</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 sz000001 业绩预告采集失败" }
```
</details>

---

## `POST /data/minute/{symbol}/refresh` — 刷新分时

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `days` | integer | 1 | 取值范围 1-5 |

```http
POST /api/v1/data/minute/hk00700/refresh?days=1 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "time": "2026-06-04T10:00:00+08:00",
      "price": 380.0,
      "volume": 1234567,
      "avg_price": 380.0,
      "source": "westock",
      "collected_at": "2026-06-04T10:30:00+08:00"
    }
  ],
  "total": 240
}
```
</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "标的 hk00700 分时数据采集失败" }
```
</details>

---

## `GET /data/etf/{symbol}` — ETF 基本信息

```http
GET /api/v1/data/etf/sh510300 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "id": 1,
  "code": "sh510300",
  "date": "2026-06-04",
  "etf_type": "股票型",
  "establish_date": "2012-05-28",
  "track_index_code": "000300",
  "track_index_name": "沪深300",
  "manage_institution": "某基金公司",
  "close_price": 4.2,
  "change_pct": 0.5,
  "total_mv": 320000000000.0,
  "shares": 76000000000.0,
  "shares_chg": 50000000.0,
  "nav": 4.205,
  "disc": -0.12,
  "ytd_return": 8.5,
  "return_1m": 1.2,
  "return_3m": 5.6,
  "return_6m": 12.3,
  "return_1y": 18.7,
  "return_3y": 25.4,
  "max_drawdown_1m": -2.1,
  "max_drawdown_3m": -5.4,
  "max_drawdown_6m": -8.2,
  "max_drawdown_1y": -12.5,
  "max_drawdown_3y": -28.0,
  "source": "westock",
  "collected_at": "2026-06-04T16:00:00+08:00"
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "ETF sh510300 无基本信息数据" }
```
</details>

---

## `GET /data/etf/{symbol}/holdings` — ETF 成分股

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 50 | 取值范围 1-200 |

```http
GET /api/v1/data/etf/sh510300/holdings?limit=20 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh510300",
  "items": [
    {
      "id": 1,
      "code": "sh510300",
      "constituent_code": "sh600519",
      "constituent_name": "贵州茅台",
      "ratio": 5.8,
      "date": "2026-06-04",
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 20
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "ETF sh510300 无成分股数据" }
```
</details>

---

## `GET /data/etf/{symbol}/nav` — ETF 历史净值

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 60 | 取值范围 1-365 |
| `from` | date | — | 起始日期 YYYY-MM-DD（内存过滤） |
| `to` | date | — | 结束日期 YYYY-MM-DD（内存过滤） |

```http
GET /api/v1/data/etf/sh510300/nav?limit=30 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh510300",
  "items": [
    {
      "id": 1,
      "code": "sh510300",
      "date": "2026-06-04",
      "nav": 4.205,
      "nav_change": 0.012,
      "nav_change_pct": 0.29,
      "acc_nav": 1.85,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 30
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "ETF sh510300 无净值数据" }
```
</details>

---

## `GET /data/etf/{symbol}/holders` — ETF 持有人结构

```http
GET /api/v1/data/etf/sh510300/holders HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "id": 1,
  "code": "sh510300",
  "report_date": "2025-12-31",
  "holder_account": 1500000,
  "individual_holder_share": 30000000000.0,
  "individual_holder_ratio": 9.4,
  "institution_holder_share": 290000000000.0,
  "institution_holder_ratio": 90.6,
  "top10_share": 180000000000.0,
  "top10_ratio": 56.3,
  "source": "westock",
  "collected_at": "2026-06-04T16:00:00+08:00"
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "ETF sh510300 无持有人数据" }
```
</details>

---

## `GET /data/etf/{symbol}/financial` — ETF 资产配置

```http
GET /api/v1/data/etf/sh510300/financial HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "id": 1,
  "code": "sh510300",
  "date": "2026-06-04",
  "total_assets": 320000000000.0,
  "stock_ratio": 98.5,
  "bond_ratio": 0.0,
  "commodity_ratio": 0.0,
  "fund_ratio": 0.0,
  "key_asset_ratio": 95.0,
  "source": "westock",
  "collected_at": "2026-06-04T16:00:00+08:00"
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "ETF sh510300 无资产配置数据" }
```
</details>

---

## `POST /data/etf-refresh/{symbol}` — 刷新 ETF 全套

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `start` | string (date) | 必填 | 净值起始日期 YYYY-MM-DD |
| `end` | string (date) | 必填 | 净值结束日期 YYYY-MM-DD |

一次性采集 5 类数据（info/holdings/nav/holders/financial），并发执行，任一失败不影响其它。

```http
POST /api/v1/data/etf-refresh/sh510300?start=2026-05-01&end=2026-06-04 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh510300",
  "summary": {
    "info":      { "success": true,  "items": 1 },
    "holdings":  { "success": true,  "items": 50 },
    "nav":       { "success": true,  "items": 30 },
    "holders":   { "success": true,  "items": 1 },
    "financial": { "success": true,  "items": 1 }
  },
  "start": "2026-05-01",
  "end": "2026-06-04"
}
```
</details>

---

## `GET /data/sectors/board` — 板块首页（行业/概念涨幅榜）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `sector_type` | string | — | industry \| concept \| fund_flow，None 时返回所有 |
| `date` | date | — | YYYY-MM-DD，None 时取最新；FastAPI 自动 ISO 422 校验 |
| `limit` | integer | 50 | 取值范围 1-200 |

```http
GET /api/v1/data/sectors/board?sector_type=industry&limit=20 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    {
      "id": 1,
      "name": "半导体",
      "date": "2026-06-04",
      "sector_type": "industry",
      "symbol": "BK0001",
      "change_pct": 3.5,
      "turnover_rate": 1.8,
      "change_pct_5d": 5.2,
      "change_pct_20d": 12.0,
      "lead_stock": "sh688981",
      "main_net_inflow": 1200000000.0,
      "main_net_inflow_5d": 3500000000.0,
      "up_down_ratio": 3.2,
      "rank": 1,
      "zxj": 4500.0,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 20,
  "sector_type": "industry",
  "date": null
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "无板块首页数据" }
```
</details>

---

## `GET /data/sectors/hot` — 热门板块

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 10 | 取值范围 1-50 |

注：本端点读取已落库数据；首次访问前需 POST /data/sectors/refresh 触发采集。

```http
GET /api/v1/data/sectors/hot?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    {
      "id": 1,
      "name": "人工智能",
      "date": "2026-06-04",
      "sector_type": "concept",
      "change_pct": 5.8,
      "rank": 1,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 5
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "无热门板块数据，请先调用 POST /data/sectors/refresh" }
```
</details>

---

## `POST /data/sectors/refresh` — 刷新板块首页 + 热门

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `hot_limit` | integer | 10 | 热门板块返回行数，取值 1-50 |

并发执行 board + hot 采集，任一失败不影响其它。

```http
POST /api/v1/data/sectors/refresh?hot_limit=10 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "summary": {
    "board": { "success": true,  "items": 80 },
    "hot":   { "success": true,  "items": 10 }
  },
  "hot_limit": 10
}
```
</details>

---

## `GET /data/finance/us/{symbol}` — 美股财务

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `period_type` | string | — | annual \| quarter，None 时返回所有 |
| `limit` | integer | 20 | 取值范围 1-100 |

```http
GET /api/v1/data/finance/us/usAAPL?period_type=quarter&limit=8 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "usAAPL",
  "items": [
    {
      "id": 1,
      "symbol": "usAAPL",
      "end_date": "2026-03-31",
      "period_type": "quarter",
      "currency": "USD",
      "period_mark": "FY2026Q2",
      "revenue": 94800000000.0,
      "net_income": 24500000000.0,
      "gross_profit": 42000000000.0,
      "operating_income": 29000000000.0,
      "ebitda": 32000000000.0,
      "ebit": 28000000000.0,
      "basic_eps": 1.62,
      "diluted_eps": 1.60,
      "total_assets": 350000000000.0,
      "total_liabilities": 280000000000.0,
      "total_equity": 70000000000.0,
      "operating_cashflow": 26000000000.0,
      "investing_cashflow": -3000000000.0,
      "financing_cashflow": -15000000000.0,
      "capex": -2500000000.0,
      "raw_json": null,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "美股 usAAPL 无财务数据" }
```
</details>

---

## `GET /data/finance/hk/{symbol}` — 港股财务

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `period_type` | string | — | annual \| quarter，None 时返回所有 |
| `limit` | integer | 20 | 取值范围 1-100 |

底层与 `/finance/us/{symbol}` 共享 us_financials 表，currency 字段区分 USD/HKD。

```http
GET /api/v1/data/finance/hk/hk00700?limit=4 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "id": 1,
      "symbol": "hk00700",
      "end_date": "2026-03-31",
      "period_type": "quarter",
      "currency": "HKD",
      "period_mark": "2026Q1",
      "revenue": 159500000000.0,
      "net_income": 41900000000.0,
      "operating_income": 55000000000.0,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "港股 hk00700 无财务数据" }
```
</details>

---

## `POST /data/finance-refresh/{symbol}` — 刷新港美股财务

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `num` | integer | 4 | 报告期数，取值 1-12 |

symbol 前缀自动判断：us → 美股 / hk → 港股。

```http
POST /api/v1/data/finance-refresh/usAAPL?num=8 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "usAAPL",
  "summary": {
    "finance": { "success": true, "items": 8 }
  },
  "num": 8
}
```
</details>

<details>
<summary>错误 400 — 无效 symbol 前缀</summary>

```json
{ "error": "INVALID_SYMBOL", "detail": "symbol 必须以 us/hk 开头，实际 jp7203" }
```
</details>

---

## `GET /data/calendar/ipo` — 新股日历

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `market` | string | hk | hk \| us（A 股数据源死） |
| `limit` | integer | 50 | 取值范围 1-200 |

```http
GET /api/v1/data/calendar/ipo?market=hk&limit=20 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "items": [
    {
      "id": 1,
      "event_type": "ipo",
      "event_date": "2026-06-10",
      "symbol": "hk09988",
      "name": "示例科技",
      "market": "hk",
      "stage": "上市",
      "price": 50.0,
      "listing_date": "2026-06-10",
      "sgrq": "2026-05-20",
      "ssrq": "2026-05-25",
      "ex_div_date": null,
      "pay_date": null,
      "report_end_date": null,
      "dividend_per_share": null,
      "currency": "HKD",
      "dividend_plan": null,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 20,
  "market": "hk"
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "hk 市场无新股日历数据，请先 POST /data/calendar-refresh" }
```
</details>

---

## `GET /data/calendar/exdiv/{symbol}` — 除权日历

```http
GET /api/v1/data/calendar/exdiv/hk00700 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "id": 1,
      "event_type": "exdiv",
      "event_date": "2026-05-15",
      "symbol": "hk00700",
      "name": "腾讯控股",
      "market": "hk",
      "stage": null,
      "price": null,
      "listing_date": null,
      "sgrq": null,
      "ssrq": null,
      "ex_div_date": "2026-05-15",
      "pay_date": "2026-06-01",
      "report_end_date": "2025-12-31",
      "dividend_per_share": 3.40,
      "currency": "HKD",
      "dividend_plan": "末期息",
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "hk00700 无除权数据，请先 POST /data/calendar-refresh" }
```
</details>

---

## `POST /data/calendar-refresh` — 刷新新股/除权日历

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `market` | string | hk | hk \| us |
| `exdiv_symbol` | string | — | exdiv 采集的股票代码（不填则跳过 exdiv） |

```http
POST /api/v1/data/calendar-refresh?market=hk&exdiv_symbol=hk00700 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "summary": {
    "ipo":   { "success": true,  "items": 12 },
    "exdiv": { "success": true,  "items": 1 }
  },
  "market": "hk",
  "exdiv_symbol": "hk00700"
}
```
</details>

---

## `GET /data/chip/{symbol}` — 筹码成本

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |

```http
GET /api/v1/data/chip/sh600519?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "date": "2026-06-04",
      "close_price": 1680.0,
      "chip_profit_rate": 65.5,
      "chip_avg_cost": 1450.0,
      "chip_concentration_90": 5.8,
      "chip_concentration_70": 4.2,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "sh600519 无筹码数据" }
```
</details>

---

## `GET /data/margintrade/{symbol}` — 融资融券

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |

```http
GET /api/v1/data/margintrade/sh600519?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "date": "2026-06-04",
      "close_price": 1680.0,
      "change_pct": 0.5,
      "finance_value": 12000000000.0,
      "security_value": 800000000.0,
      "finance_buy_value": 250000000.0,
      "finance_refund_value": 180000000.0,
      "trading_value": 430000000.0,
      "trading_value_dif": 70000000.0,
      "finance_value_dod": 80000000.0,
      "security_value_dod": 5000000.0,
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```
</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "sh600519 无融资融券数据" }
```
</details>

---

## `GET /data/blocktrade/{symbol}` — 大宗交易

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |

```http
GET /api/v1/data/blocktrade/sh600519?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "date": "2026-06-04",
      "close_price": 1680.0,
      "change_pct": 0.5,
      "turnover_price": 1650.0,
      "turnover_value": 330000000.0,
      "close_discount_rate": -1.79,
      "buy_department": "[\"机构专用\", \"华泰证券益田路\"]",
      "sell_department": "[\"海通证券上海某营业部\"]",
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```

> `buy_department` / `sell_department` 为 JSON 数组字符串（同一 (symbol, date) 可能多笔）；
> 明细表 2 缺失或列名不匹配时回落 `null`（向后兼容旧 CLI 输出）。
> 客户端需 `json.loads()` 解析。

</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "sh600519 无大宗交易数据" }
```
</details>

---

## `GET /data/lhb/{symbol}` — 龙虎榜

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 20 | 取值范围 1-200 |

```http
GET /api/v1/data/lhb/sh600519?limit=5 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "items": [
    {
      "id": 1,
      "symbol": "sh600519",
      "date": "2026-06-04",
      "name": "贵州茅台",
      "close_price": 1680.0,
      "change_pct": 0.5,
      "net_buy_amount": 85000000.0,
      "buy_department": "[\"东方证券上海某营业部\"]",
      "sell_department": "[\"中信证券北京某营业部\"]",
      "reason": "日涨幅偏离值达 7%",
      "source": "westock",
      "collected_at": "2026-06-04T16:00:00+08:00"
    }
  ],
  "total": 1
}
```

> `buy_department` / `sell_department` 为 JSON 数组字符串（同一 (symbol, date) 可能多条记录）；
> 明细表 2 缺失或列名不匹配时回落 `null`（向后兼容旧 CLI 输出）。
> 客户端需 `json.loads()` 解析。

</details>

<details>
<summary>错误 404 — 无数据</summary>

```json
{ "error": "NO_DATA", "detail": "sh600519 无龙虎榜数据" }
```
</details>

---

## `POST /data/chip-refresh/{symbol}` — 刷新筹码+融资融券

无日期参数；同时触发 chip_distribution + margintrade 采集，并发执行。

```http
POST /api/v1/data/chip-refresh/sh600519 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "summary": {
    "chip":        { "success": true },
    "margintrade": { "success": true }
  }
}
```
</details>

---

## `POST /data/blocktrade-refresh/{symbol}` — 刷新大宗交易

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `date` | string (date) | 必填 | YYYY-MM-DD |

```http
POST /api/v1/data/blocktrade-refresh/sh600519?date=2026-06-04 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "date": "2026-06-04",
  "data": [
    {
      "turnover_price": 1650.0,
      "turnover_value": 330000000.0,
      "close_discount_rate": -1.79,
      "buy_department": "[\"机构专用\", \"华泰证券益田路\"]",
      "sell_department": "[\"海通证券上海某营业部\"]"
    }
  ]
}
```

> `buy_department` / `sell_department` 为 JSON 数组字符串（多笔合并）。

</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "sh600519 大宗交易采集失败" }
```
</details>

---

## `POST /data/lhb-refresh/{symbol}` — 刷新龙虎榜

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `date` | string (date) | 必填 | YYYY-MM-DD |

```http
POST /api/v1/data/lhb-refresh/sh600519?date=2026-06-04 HTTP/1.1
X-API-Key: marketlens-local
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "sh600519",
  "date": "2026-06-04",
  "data": [
    {
      "name": "贵州茅台",
      "close_price": 1680.0,
      "net_buy_amount": 85000000.0,
      "buy_department": "[\"东方证券上海某营业部\"]",
      "sell_department": "[\"中信证券北京某营业部\"]",
      "reason": "日涨幅偏离值达 7%"
    }
  ]
}
```

> `buy_department` / `sell_department` 为 JSON 数组字符串（多行合并）。

</details>

<details>
<summary>错误 502 — 采集失败</summary>

```json
{ "error": "COLLECT_FAILED", "detail": "sh600519 龙虎榜采集失败" }
```
</details>
