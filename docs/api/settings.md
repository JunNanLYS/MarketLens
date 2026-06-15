# 可编辑配置 API

> 基准路径: `/api/v1/settings` | 接口数: 3 | 返回上级: [API 概述](/docs/api.md)

---

## 用途

`Settings` 是给前端 Settings 页面提供的"在线改 `config.yaml` + 立即生效"端点。后端 `ConfigStore`（`backend/config_runtime.py`）是单例，启动时加载一次到内存，`update_with_special_handling` 写回时：

1. 按白名单校验 key（仅 `data_sources.*` / `scheduler.tasks.*` 路径，避免误改 `security.cors_origins` 等）
2. 写入前备份 `config.yaml` → `config.yaml.bak`（一键回滚）
3. 原子写回（先 `.tmp` 再 `os.replace`）
4. 触发 reload 钩子 —— 数据源 Provider 链和 Scheduler 任务间隔同步更新

---

## 鉴权

| 方法 | 是否需要 API Key |
|---|---|
| `GET` | 否 |
| `PATCH` | **是**（需 `X-API-Key` 头，会落盘 `config.yaml`） |
| `POST` (`/rollback`) | **是**（需 `X-API-Key` 头，恢复 `.bak`） |

API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。

---

## 接口清单

| 方法 | 路径 | 用途 | 状态码 |
|---|---|---|---|
| `GET` | `/settings` | 查询所有可编辑项 | 200 |
| `PATCH` | `/settings` | 应用 diff | 200, 400, 401 |
| `POST` | `/settings/rollback` | 从 `.bak` 恢复 | 200, 400, 401 |

---

## `GET /settings`

返回当前可编辑项的快照（仅白名单字段，不暴露 `security.cors_origins` 等敏感配置）。

```http
GET /api/v1/settings HTTP/1.1
```

<details>
<summary>响应 200</summary>

```json
{
  "editable": {
    "sources": [
      {
        "group": "structured",
        "name": "westock",
        "provider": "WeStockProvider",
        "enabled": true,
        "optional": false,
        "timeout": 30
      },
      {
        "group": "news",
        "name": "bbc_world",
        "provider": "RSSProvider",
        "enabled": true,
        "optional": true,
        "timeout": 30
      }
    ],
    "scheduler": {
      "tasks": {
        "quote":        { "interval": 15 },
        "daily_close":  { "cron": "0 16 * * 1-5" },
        "news":         { "interval": 60 },
        "ai_report":    { "cron": "0 20 * * *" },
        "cleanup":      { "cron": "30 3 * * *" }
      }
    }
  }
}
```
</details>

**`sources[]` 字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `group` | string | `structured` / `news` |
| `name` | string | `config.yaml` 中 `data_sources.{group}[]` 的 `name` |
| `provider` | string | `BaseProvider` 子类名（只读，不可改） |
| `enabled` | bool | 是否启用 |
| `optional` | bool | 失败时是否静默降级（只读） |
| `timeout` | int | 单次请求超时秒数 |

**`scheduler.tasks.<name>.{interval,cron}` 字段**：

- `interval`：整数分钟（如 `15` / `60`），由 APScheduler `IntervalTrigger(minutes=...)` 解析
- `cron`：5 字段 cron 表达式，由 APScheduler `CronTrigger` 解析
- 二者互斥 —— `interval` 任务改 `cron` 字段会被忽略（反之亦然）

---

## `PATCH /settings` — 应用 diff

前端提交的 `updates` 字段是 dotted-key → value 映射。请求体：

```http
PATCH /api/v1/settings HTTP/1.1
Content-Type: application/json
X-API-Key: marketlens-local

{
  "updates": {
    "data_sources.structured.sina":     { "enabled": false, "timeout": 45 },
    "data_sources.news.bbc_world":      { "enabled": true, "timeout": 30 },
    "scheduler.tasks.quote.interval":   10
  }
}
```

**支持两类 key**：

| key 形式 | 语义 | value 类型 |
|---|---|---|
| `data_sources.<group>.<name>` | 整条 source dict 替换（保留 `name` / `provider` / `optional`） | `dict {enabled, timeout}` |
| `scheduler.tasks.<task>.interval` | 任务间隔 | `int`（分钟，1~1440） |
| `scheduler.tasks.<task>.cron` | CRON 表达式 | `string` |

**生效行为**：

- `data_sources.*` 改动 → Provider 链立刻重建（`CollectionService._init_providers` 钩子），下一次 `collect_quotes` 看到的是新 `enabled` 状态
- `scheduler.tasks.quote.interval` 改动 → APScheduler `reschedule_job` 立刻生效
- `scheduler.tasks.daily_close.cron` 改动 → 同上，立即更新 cron 表达式

<details>
<summary>错误 400 — INVALID_SETTING</summary>

```json
{
  "detail": {
    "error": "INVALID_SETTING",
    "detail": "key 'data_sources.structured.sina.timeout' 必须 > 0"
  }
}
```
</details>

---

## `POST /settings/rollback`

把 `config.yaml` 恢复为最近一次修改前的 `.bak` 副本，触发 reload 钩子。

```http
POST /api/v1/settings/rollback HTTP/1.1
X-API-Key: marketlens-local
```

**前置条件**：必须存在 `config.yaml.bak`（由最近一次 PATCH 生成）。如果没有 `.bak`，返回 `400 ROLLBACK_FAILED`。

**使用场景**：

- 改了 `enabled: false` 后发现定时任务全没数据 → 一键 rollback
- 改错 cron 表达式导致任务再也不触发 → rollback 回退到上次正常状态

<details>
<summary>错误 400 — ROLLBACK_FAILED</summary>

```json
{
  "detail": {
    "error": "ROLLBACK_FAILED",
    "detail": "config.yaml.bak 不存在,无法回滚"
  }
}
```
</details>

---

## 字段联动与限制

- **白名单**：`data_sources.*` 和 `scheduler.tasks.*` 之外的所有 key 都会被 400 拒绝（如 `security.api_key`、`cleanup.retention_days`）
- **保留字段**：`name` / `provider` / `optional` 在 PATCH 时被服务端强制保留，不允许修改
- **`timeout` 范围**：`1 ≤ timeout ≤ 600` 秒
- **`interval` 范围**：`1 ≤ interval ≤ 1440` 分钟（整数）
- **原子性**：写回采用 `tempfile + os.replace`，写盘中途崩溃不会留下半截 `config.yaml`
- **并发**：单例内 `threading.Lock` 保护，并发 PATCH 串行执行

---

## 相关端点

- `GET /api/v1/data-sources/config` — 数据源**只读**快照（轻量级，不触发 ConfigStore 读取）
- `GET /api/v1/data-sources/status` — 数据源**配置 + 健康**（含 NeoData token 状态、command 路径解析）
- `GET /api/v1/tasks/status` — 任务最新一次 `run_logs`（确认改动是否影响执行）
