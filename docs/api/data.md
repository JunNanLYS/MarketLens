# 市场数据 API

> 基准路径: `/api/v1/data` | 返回上级: [API 概述](../api.md)

---

## 接口清单

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/data/quotes/{symbol}` | 最新行情 | 200, 404 |
| `GET` | `/data/quotes/{symbol}/history` | 历史行情序列 | 200, 404 |
| `GET` | `/data/kline/{symbol}` | 日 K 线 | 200, 404 |
| `GET` | `/data/finance/{symbol}` | 财务数据 | 200, 404 |
| `GET` | `/data/fund-flow/{symbol}` | 资金流向 | 200, 404 |
| `GET` | `/data/technical/{symbol}` | 技术指标 | 200, 404 |

> 所有数据均包含 `source` 和 `collected_at` 字段以支持追溯。

---

## `GET /data/quotes/{symbol}` — 最新行情

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `force` | boolean | false | 强制实时采集 |

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

## `GET /data/quotes/{symbol}/history` — 历史行情

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `from` | datetime | — | 起始时间（ISO 8601） |
| `to` | datetime | — | 结束时间 |
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

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | integer | 60 | 最大 365 |
| `from` | date | — | 起始日期 `YYYY-MM-DD` |
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
| `period` | string | 最新 | 报告期 `YYYYQN`，如 `2026Q1` |
| `limit` | integer | 4 | 返回最近 N 期 |

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

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `days` | integer | 5 | 最大 30 |

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
  "macd": { "dif": 2.8, "dea": 2.1, "histogram": 0.7, "signal": "金叉" },
  "rsi": { "rsi6": 58.3, "rsi14": 54.7 },
  "boll": { "upper": 392.0, "middle": 378.0, "lower": 364.0, "position": "中轨上方" },
  "volume_ma": { "ma5": 21000000, "ma20": 19500000 },
  "source": "westock",
  "collected_at": "2026-05-31T16:05:00+08:00"
}
```
</details>

---

## `GET /data/intraday/{symbol}` — 分时数据

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `days` | integer | 1 | 最近 N 日分时（最大 5） |

```http
GET /api/v1/data/intraday/hk00700?days=1 HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "symbol": "hk00700",
  "items": [
    {
      "symbol": "hk00700",
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

> 分时数据实时采集，不落库缓存。

---

## `GET /data/shareholder/{symbol}` — 股东结构

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

> 股东结构数据实时采集，不落库缓存。包含十大股东列表和股东人数变化历史。

---

## `GET /data/reserve/{symbol}` — 业绩预告

```http
GET /api/v1/data/reserve/sz000001 HTTP/1.1
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

> 业绩预告数据实时采集，返回最新一条预告。
