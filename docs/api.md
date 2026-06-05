# MarketLens API 文档

> 版本: v2 | 基准路径: `http://localhost:8000/api/v1` | 协议: HTTP / HTTPS | 内容类型: `application/json; charset=utf-8`
> 文档校验基准: `backend/api/*.py` + `backend/main.py`（共 40 个业务接口 + 1 个数据源状态 + 1 个健康检查 + 1 个根路径）

---

## 快速导航

| 资源组 | 文档 | 接口数 |
|---|---|---|
| 🏷️ 标的管理 | [assets](api/assets.md) | 6 |
| 📊 市场数据 | [data](api/data.md) | 11 |
| 📰 新闻 | [news / reports / tasks](api/news-reports-tasks.md#新闻) | 2 |
| 🧠 AI 报告 | [news / reports / tasks](api/news-reports-tasks.md#ai-报告) | 4 |
| ⏰ 任务管理 | [news / reports / tasks](api/news-reports-tasks.md#任务管理) | 3 |
| 🔑 NeoData Token | [neodata](api/neodata.md) | 2 |
| 💼 投资组合 | [portfolio](api/portfolio.md) | 12 |
| 🩺 系统 | `GET /api/v1/health` | 1 |

---

## 一页速览（41 个接口）

| 方法 | 路径 | 鉴权 | 用途 | 主要状态码 |
|---|---|---|---|---|
| `GET` | `/api/v1/health` | — | 健康检查 | 200 |
| `GET` | `/assets` | — | 追踪列表 | 200 |
| `POST` | `/assets` | 🔑 | 添加标的 | 201 / 400 / 409 |
| `GET` | `/assets/search` | — | 搜索外部标的 | 200 / 400 |
| `GET` | `/assets/{id}` | — | 标的详情（聚合） | 200 / 404 |
| `PATCH` | `/assets/{id}` | 🔑 | 部分更新 | 200 / 404 |
| `DELETE` | `/assets/{id}` | 🔑 | 删除 | 204 / 404 |
| `GET` | `/data/quotes/{symbol}` | — | 最新行情 | 200 / 404 |
| `POST` | `/data/quotes/{symbol}/refresh` | — | 手动刷新行情 | 200 / 502 |
| `GET` | `/data/quotes/{symbol}/history` | — | 历史行情 | 200 / 404 / 422 |
| `GET` | `/data/kline/{symbol}` | — | 日 K 线 | 200 / 404 / 422 |
| `GET` | `/data/finance/{symbol}` | — | 财务数据 | 200 / 404 |
| `GET` | `/data/fund-flow/{symbol}` | — | 资金流向 | 200 / 404 / 422 |
| `GET` | `/data/technical/{symbol}` | — | 技术指标 | 200 / 404 |
| `POST` | `/data/intraday/{symbol}` | — | 分时数据采集 | 200 / 422 / 502 |
| `POST` | `/data/shareholder/{symbol}` | — | 股东结构采集 | 200 / 502 |
| `POST` | `/data/dividend/{symbol}` | — | 分红数据采集 | 200 / 502 |
| `POST` | `/data/reserve/{symbol}` | — | 业绩预告采集 | 200 / 502 |
| `GET` | `/news` | — | 新闻列表 | 200 |
| `GET` | `/news/{id}` | — | 新闻详情 | 200 / 404 |
| `GET` | `/reports` | — | 报告列表 | 200 |
| `GET` | `/reports/{symbol}` | — | 标的最新报告 | 200 / 404 |
| `GET` | `/reports/{symbol}/history` | — | 历史报告 | 200 |
| `POST` | `/reports/generate` | 🔑 | 手动生成报告 | 200 |
| `GET` | `/tasks/status` | — | 任务状态 | 200 / 503 |
| `POST` | `/tasks/trigger/{name}` | 🔑 | 手动触发 | 202 / 401 / 404 / 500 / 503 |
| `GET` | `/tasks/logs` | — | 运行日志 | 200 |
| `GET` | `/neodata/token-status` | — | Token 状态 | 200 |
| `POST` | `/neodata/token` | 🔑 | 保存 Token | 200 / 401 |
| `POST` | `/accounts` | 🔑 | 创建账户 | 201 / 400 / 409 |
| `GET` | `/accounts` | — | 账户列表 | 200 |
| `GET` | `/accounts/{account_id}` | — | 账户详情 | 200 / 404 |
| `PATCH` | `/accounts/{account_id}` | 🔑 | 更新账户 | 200 / 400 / 404 / 409 |
| `DELETE` | `/accounts/{account_id}` | 🔑 | 删除账户（软删除） | 204 / 404 |
| `POST` | `/transactions` | 🔑 | 录入交易 | 201 / 400 / 404 |
| `GET` | `/transactions` | — | 交易历史 | 200 |
| `GET` | `/transactions/{transaction_id}` | — | 交易详情 | 200 / 404 |
| `PATCH` | `/transactions/{transaction_id}` | 🔑 | 更新交易 | 200 / 400 / 404 |
| `DELETE` | `/transactions/{transaction_id}` | 🔑 | 删除交易（软删除） | 204 / 400 / 404 |
| `GET` | `/positions` | — | 持仓总览 | 200 |
| `GET` | `/positions/realized-pnl` | — | 已实现盈亏 | 200 |

> 🔑 = 写端点，需要 `X-API-Key` 请求头，详见下文「鉴权」章节。

---

## 通用约定

### 鉴权（v2 新增）

写端点采用单密钥鉴权。所有对数据库产生写入、触发副作用或更新凭证的接口必须携带 `X-API-Key` 请求头，否则返回 `401 UNAUTHORIZED`。

| 项 | 说明 |
|---|---|
| 请求头 | `X-API-Key: <your-key>` |
| 优先级 | 环境变量 `MARKETLENS_API_KEY` > `config.security.api_key` |
| 默认值 | `marketlens-local`（仅限本地开发使用） |
| 启动告警 | 检测到默认 key 未被环境变量覆盖时记录 WARNING |
| 失败响应 | `401 {"error": "UNAUTHORIZED", "detail": "无效或缺失的 API Key"}` |

**受保护端点清单**：

| 资源组 | 端点 |
|---|---|
| 标的管理 | `POST /assets`、`PATCH /assets/{id}`、`DELETE /assets/{id}` |
| 投资组合 | `POST /accounts`、`PATCH /accounts/{id}`、`DELETE /accounts/{id}`、`POST /transactions`、`PATCH /transactions/{transaction_id}`、`DELETE /transactions/{transaction_id}` |
| AI 报告 | `POST /reports/generate` |
| 任务管理 | `POST /tasks/trigger/{name}` |
| NeoData | `POST /neodata/token` |

> 所有 `GET` 端点（除 `/api/v1/health` 外的读操作）均无需鉴权。

**配置示例**（`config.yaml`）：

```yaml
security:
  api_key: "your-strong-key-here"   # 生产环境必须覆盖
  cors_origins: ["http://localhost:8501"]
```

**调用示例**：

```bash
curl -X POST http://localhost:8000/api/v1/accounts \
  -H "X-API-Key: marketlens-local" \
  -H "Content-Type: application/json" \
  -d '{"name": "我的账户"}'
```

### Security 响应头（v2 新增）

`SecurityHeadersMiddleware`（注册于 CORS 之前）会向所有响应注入以下安全头，覆盖 401/4xx/5xx 错误响应：

| 响应头 | 值 | 作用 |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | 禁止浏览器 MIME 嗅探 |
| `X-Frame-Options` | `DENY` | 禁止任何 iframe 嵌入 |
| `Referrer-Policy` | `no-referrer` | 出口链路不携带来源 |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | 强制 HTTPS（生产环境） |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'` | CSP 保持宽松以兼容 FastAPI Swagger UI |

### CORS

| 项 | 默认值 | 配置字段 |
|---|---|---|
| Origins | `["http://localhost:8501", "http://127.0.0.1:8501"]` | `security.cors_origins` |
| Methods | `["GET", "POST", "PUT", "DELETE", "PATCH"]` | `security.cors_methods` |
| Headers | `["Content-Type", "Authorization", "X-API-Key"]` | `security.cors_headers` |

> 严禁在生产环境使用通配符 `*`；如有需要请在 `config.yaml` 显式声明。

### 分页

所有列表接口统一使用页码分页：

```
?page=1&page_size=20
```

| 参数 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `page` | 1 | ≥1 | 页码 |
| `page_size` | 20 | 1–100 | 单页条目数（部分接口上限为 500/365/90/20，依业务而定） |

响应包裹：

```json
{
  "items": [...],
  "page_info": { "page": 1, "page_size": 20, "total": 156, "total_pages": 8 }
}
```

> 部分实时采集接口（如 `/data/positions`、`/data/positions/realized-pnl`）直接返回数组，不使用页码分页。

### 错误响应

统一格式：

```json
{ "error": "ERROR_CODE", "detail": "人类可读的描述" }
```

部分接口（如 `POST /assets`）使用 `message` 字段携带业务文案，例如 `409 ASSET_EXISTS` 时返回 `existing_asset` 子对象。

未捕获异常走全局处理器：

```json
{ "error": "INTERNAL_ERROR", "detail": "内部服务错误" }
```

### 时间格式

ISO 8601 带时区：`"2026-05-31T15:30:00+08:00"`。日期（无时间）使用 `YYYY-MM-DD`。

### 数据溯源

所有数据响应均含 `source`（数据源枚举）和 `collected_at`（采集时间）字段。AI 报告额外包含 `data_used`，列出本次分析引用的全部数据源与采集时间，杜绝幻觉。

---

## 错误码速查

| 状态码 | 错误码 | 触发场景 |
|---|---|---|
| `400` | `INVALID_SYMBOL` | 代码格式错误 / 无法识别 |
| `400` | `INVALID_INPUT` | 字段类型或业务规则校验失败 |
| `400` | `BAD_REQUEST` | 通用参数错误 |
| `400` | `INSUFFICIENT_HOLDING` | 卖出数量超过当前持仓 |
| `401` | `UNAUTHORIZED` | 写端点缺失或错误的 `X-API-Key` |
| `404` | `ASSET_NOT_FOUND` | 标的 ID 不存在 |
| `404` | `ACCOUNT_NOT_FOUND` | 账户 ID 不存在 |
| `404` | `TRANSACTION_NOT_FOUND` | 交易 ID 不存在 |
| `404` | `SYMBOL_NOT_FOUND` | 标的代码无数据 |
| `404` | `NEWS_NOT_FOUND` | 新闻 ID 不存在 |
| `404` | `REPORT_NOT_FOUND` | 标的尚无 AI 报告 |
| `404` | `TASK_NOT_FOUND` | `task_name` 不在 `VALID_TASK_NAMES` 中 |
| `409` | `ASSET_EXISTS` | 标的代码已在追踪列表 |
| `409` | `ACCOUNT_EXISTS` | 账户名称重复 |
| `422` | `VALIDATION_FAILED` | Pydantic 字段校验失败（默认 FastAPI 行为） |
| `500` | `INTERNAL_ERROR` | 未捕获的服务端异常 |
| `500` | `TRIGGER_FAILED` | 任务调度器触发任务失败 |
| `502` | `REFRESH_FAILED` | 行情刷新时所有数据源失败 |
| `502` | `COLLECT_FAILED` | 实时采集（分时/股东/分红/业绩预告）失败 |
| `503` | `SCHEDULER_NOT_READY` | 调度器未初始化（应用启动中） |

---

## 枚举值

| 枚举 | 可选值 |
|---|---|
| `market` | `sh` / `sz` / `hk` / `us` / `bj`（北交所） / `gb`（股转） |
| `asset_type` | `stock` / `etf` / `index` / `future`（MVP）；`forex` / `commodity`（预留） |
| `action`（AI 建议） | `buy` / `sell` / `watch` / `avoid` |
| `risk_level` | `low` / `medium` / `high` |
| `sentiment` | `positive` / `negative` / `neutral` |
| `source`（数据源） | `westock` / `sina` / `sina_rss` / `neodata` |
| `task_name` | `quote` / `daily_close` / `news` / `ai_report` / `cleanup` |
| `transaction_type` | `buy` / `sell` / `dividend` / `split` |
| `run_log.status` | `success` / `failed` / `running` |

---

## RESTful 设计原则

| # | 原则 | 体现 |
|---|---|---|
| 1 | 名词复数资源 | `/assets` 而非 `/getAssets` |
| 2 | 方法语义正确 | `GET` 只读，`POST` 创建，`PATCH` 部分更新，`DELETE` 删除 |
| 3 | 避免路径动词 | `POST /assets/search` 作为搜索资源操作 |
| 4 | 动作名词化 | `POST /reports/generate`、`POST /data/intraday/{symbol}` 建模为生成 / 采集资源 |
| 5 | 层级 ≤ 2 层 | `/assets/{id}`、`/reports/{symbol}/history` |
| 6 | 版本化 | `/api/v1/` 路径前缀，开放演进 |
| 7 | 写端点鉴权 | 所有非 `GET` 端点需 `X-API-Key` 头，避免 CSRF 与未授权写入 |

---

## 安全注意事项

1. **生产环境必须覆盖默认 API Key**。`marketlens-local` 仅用于本地单用户场景；通过 `MARKETLENS_API_KEY` 环境变量或 `config.security.api_key` 覆盖，否则攻击者可绕过鉴权。
2. **部署必须启用 HTTPS**。`Strict-Transport-Security` 头依赖 TLS；仅在生产环境前置 Nginx/Caddy 反向代理时生效。
3. **CORS 来源最小化**。默认仅放行 `http://localhost:8501`（Streamlit UI）；其他前端需要显式加入 `security.cors_origins`。
4. **Swagger UI 在线文档**。开发环境访问 `/docs` 与 `/redoc`；生产环境建议禁用或将文档路由放在鉴权之后。
5. **NeoData Token 持久化**。`POST /neodata/token` 写入 `~/.workbuddy/.neodata_token`，请确保主目录权限为 `0700`。
