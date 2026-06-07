# 投资组合管理 API

> 基准路径: `/api/v1` | 返回上级: [API 概述](/docs/api.md)

---

## 鉴权

| 方法 | 是否需要 API Key |
|---|---|
| `GET` | 否 |
| `POST` / `PATCH` / `DELETE` | 是（需 `X-API-Key` 头） |

API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。

---

## 接口清单

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `POST` | `/accounts` | 创建账户 | 201, 400, 401, 409 |
| `GET` | `/accounts` | 账户列表 | 200 |
| `GET` | `/accounts/{account_id}` | 账户详情 | 200, 404 |
| `PATCH` | `/accounts/{account_id}` | 更新账户 | 200, 400, 401, 404, 409 |
| `DELETE` | `/accounts/{account_id}` | 删除账户（软删除） | 204, 401, 404 |
| `POST` | `/transactions` | 录入交易 | 201, 400, 401, 404 |
| `GET` | `/transactions` | 交易历史（分页/筛选） | 200, 422 |
| `GET` | `/transactions/{transaction_id}` | 交易详情 | 200, 404 |
| `PATCH` | `/transactions/{transaction_id}` | 更新交易 | 200, 400, 401, 404, 422 |
| `DELETE` | `/transactions/{transaction_id}` | 删除交易（软删除） | 204, 400, 401, 404 |
| `GET` | `/positions` | 持仓总览 | 200 |
| `GET` | `/positions/realized-pnl` | 已实现盈亏汇总 | 200, 422 |

---

## 账户管理

### `POST /accounts` — 创建账户

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 账户名称（唯一） |
| `broker` | string | 否 | 券商名称 |
| `currency` | string | 否 | 默认币种，默认 `CNY` |
| `notes` | string | 否 | 备注 |

```json
{ "name": "富途", "broker": "富途牛牛", "currency": "HKD" }
```

<details>
<summary>成功 201</summary>

```json
{
  "id": 1, "name": "富途", "broker": "富途牛牛",
  "currency": "HKD", "notes": null,
  "created_at": "2026-05-31T10:00:00", "deleted_at": null
}
```
</details>

<details>
<summary>错误 409 — 同名账户</summary>

```json
{ "error": "ACCOUNT_EXISTS", "detail": "账户名称 '富途' 已存在" }
```
</details>

---

### `GET /accounts` — 账户列表

| 参数 | 类型 | 说明 |
|---|---|---|
| `include_deleted` | bool | 是否包含已删除账户，默认 `false` |

---

### `GET /accounts/{account_id}` — 账户详情

<details>
<summary>错误 404</summary>

```json
{ "error": "ACCOUNT_NOT_FOUND", "detail": "账户 999 不存在" }
```
</details>

---

### `PATCH /accounts/{account_id}` — 更新账户

可更新字段：`name`、`broker`、`currency`、`notes`。

---

### `DELETE /accounts/{account_id}` — 删除账户

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `soft` | bool | `true` | `true` 仅软删除（设置 `deleted_at`），`false` 物理删除 |

软删除（默认），设置 `deleted_at`。关联交易记录保留。

---

## 交易管理

### `POST /transactions` — 录入交易

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `account_id` | int | 是 | 所属账户 |
| `symbol` | string | 是 | 标的代码 |
| `type` | string | 是 | `buy` / `sell` / `dividend` / `split` |
| `quantity` | float | 是 | 数量（> 0） |
| `price` | float | 是 | 价格（> 0） |
| `fee` | float | 否 | 手续费，默认 0 |
| `currency` | string | 否 | 币种，默认从账户继承 |
| `trade_date` | string | 是 | 交易日期 |
| `notes` | string | 否 | 备注 |

<details>
<summary>成功 201</summary>

```json
{
  "id": 1, "account_id": 1, "symbol": "hk00700",
  "type": "buy", "quantity": 100, "price": 380.0,
  "fee": 0.0, "currency": "HKD", "trade_date": "2026-05-15",
  "notes": null, "created_at": "2026-05-15T10:00:00",
  "updated_at": "2026-05-15T10:00:00", "deleted_at": null
}
```
</details>

<details>
<summary>错误 400 — 卖出超过持仓</summary>

```json
{ "error": "INSUFFICIENT_HOLDING", "detail": "卖出数量 150 超过当前持仓 100" }
```
</details>

<details>
<summary>错误 404 — 账户不存在</summary>

```json
{ "error": "ACCOUNT_NOT_FOUND", "detail": "账户不存在" }
```
</details>

---

### `GET /transactions` — 交易历史

| 参数 | 类型 | 说明 |
|---|---|---|
| `account_id` | int | 筛选账户 |
| `symbol` | string | 筛选标的 |
| `type` | string | 筛选类型 |
| `date_from` | date (ISO `YYYY-MM-DD`) | 起始日期；非法格式返回 422 |
| `date_to` | date (ISO `YYYY-MM-DD`) | 结束日期；非法格式返回 422 |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页条数，默认 20 |

按 `trade_date` 倒序，然后按 `created_at` 倒序。

---

### `PATCH /transactions/{transaction_id}` — 更新交易

可更新字段：`quantity`（> 0）、`price`（> 0）、`fee`、`currency`、`trade_date`、`notes`（不可改 `account_id` / `symbol` / `type`，以保证 WAC 计算语义稳定）。

更新后验证持仓不为负。

---

### `DELETE /transactions/{transaction_id}` — 删除交易

软删除。删除后验证持仓不为负，若为负则拒绝。

<details>
<summary>错误 400 — 删除后持仓为负</summary>

```json
{ "error": "INSUFFICIENT_HOLDING", "detail": "删除后持仓将为负数 (-50.0)，不允许删除" }
```
</details>

---

## 持仓

### `GET /positions` — 持仓总览

| 参数 | 类型 | 说明 |
|---|---|---|
| `account_id` | int | 筛选账户（可选） |

实时聚合计算所有未完全卖出的标的持仓。

```json
[
  {
    "account_id": 1,
    "symbol": "hk00700",
    "name": "腾讯控股",
    "total_qty": 200,
    "avg_cost": 350.0,
    "current_price": 400.0,
    "market_value": 80000.0,
    "unrealized_pnl": 10000.0,
    "unrealized_pnl_pct": 14.29
  }
]
```

**计算规则：**
- 持仓量：buy 加、sell 减、dividend 不变、split 乘以比例
- 加权均价：每次 buy 重新计算；sell/dividend/split 不改变均价
- 市值 = 持仓量 × 最新行情价
- 浮动盈亏 = (最新行情价 - 均价) × 持仓量
- 浮动盈亏率 = (最新行情价 - 均价) / 均价 × 100

---

### `GET /positions/realized-pnl` — 已实现盈亏汇总

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `account_id` | int | — | 筛选账户（可选） |
| `symbol` | string | — | 筛选标的（可选，最小长度 1） |
| `page` | int | 1 | 页码（≥ 1） |
| `page_size` | int | 50 | 每页条数（1–200，DB 层强制 cap） |

```json
{
  "items": [
    {
      "account_id": 1,
      "symbol": "hk00700",
      "total_sell_qty": 100,
      "avg_cost": 300.0,
      "realized_pnl": 9985.0
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

**计算规则：**
- 已实现盈亏 = 卖出金额(数量×价格) - 卖出数量 × 均价 - 手续费

**分页支持：** 端点已接受 `page` / `page_size`（默认 50，上限 200），由 `PortfolioService.get_realized_pnl()` 在 DB 层按 `(account_id, symbol)` 强制聚合分页后返回，并同时返回 `total`（满足过滤条件的所有 `(account_id, symbol)` 组合总数）以便前端计算总页数。
