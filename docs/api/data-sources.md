# 数据源状态 API

> 资源路径: `/api/v1/data-sources` | 接口数: 1

---

## 用途

聚合所有已注册数据源的**配置可见性**与**健康度**,供前端状态页使用。设计目标是"显式可观察":

- 不在请求时构造任何 Provider 实例,避免已知的"Service 实例重建"问题加剧
- 不做实时连通性探测(避免请求阻塞)
- 对 NeoData 额外暴露 token 健康度(`has_token` / `token_source` / `token_expires_at`)

---

## 鉴权

无。所有字段只读,GET 不修改任何状态。

---

### `GET /status`

返回所有数据源(`structured` + `news`)的当前配置和健康状态。

**响应示例**:

```json
{
  "structured": [
    {
      "name": "westock",
      "provider": "WeStockProvider",
      "configured": true,
      "optional": false,
      "command": "npx -y westock-data-clawhub@1.0.4",
      "executable": "npx",
      "command_resolved": true
    },
    {
      "name": "sina",
      "provider": "SinaProvider",
      "configured": true,
      "optional": false,
      "endpoint": "https://hq.sinajs.cn/list={codes}"
    },
    {
      "name": "neodata",
      "provider": "NeoDataProvider",
      "configured": true,
      "optional": true,
      "endpoint": "https://copilot.tencent.com/agenttool/v1/neodata",
      "has_token": true,
      "token_source": "cache",
      "token_expires_at": "2027-04-29T20:08:57",
      "token_verified": false
    }
  ],
  "news": [
    {
      "name": "bbc_world",
      "provider": "RSSProvider",
      "configured": true,
      "optional": true,
      "endpoint": "https://feeds.bbci.co.uk/news/world/rss.xml"
    }
  ],
  "hint": "NeoData token 由外部 workbuddy 工具管理,本项目只读。"
}
```

**字段说明**:

| 字段 | 类型 | 适用源 | 说明 |
|------|------|--------|------|
| `name` | string | 全部 | `config.yaml` 中 `data_sources.{structured,news}[]` 的 name |
| `provider` | string | 全部 | `BaseProvider` 子类名 |
| `configured` | bool | 全部 | 是否启用(`enabled: true`) |
| `optional` | bool | 全部 | 失败时是否静默降级 |
| `endpoint` | string \| null | Sina / NeoData / RSS 等 | HTTP/RSS 源的 URL |
| `command` | string \| null | WeStock | 完整命令行 |
| `executable` | string \| null | WeStock | 命令首项(实际可执行文件名) |
| `command_resolved` | bool | WeStock | `shutil.which` 是否能找到该可执行文件 |
| `has_token` | bool | NeoData | 是否有可用 token(本地缓存 + config + env 优先级) |
| `token_source` | string \| null | NeoData | `cache` / `config` / `env` / `none` |
| `token_expires_at` | string \| null | NeoData | ISO 8601 过期时间(JWT `exp` 或 saved_at + 12h) |
| `token_verified` | bool | NeoData | **始终为 false**——本地无服务端公钥,不做 JWT 签名验证 |

**NeoData 字段语义**:

- `token_source: "none"` → 提示用户去 workbuddy 工具刷新凭证
- `token_source: "cache"` + `token_expires_at` 距今 < 1h → 提示 token 即将过期
- `token_verified: false` 是预期行为,不代表 token 无效,只表示本地无法做签名验证

**相关端点**:

- `GET /api/v1/tasks/logs?task_name=neodata_health` — 启动期健康检查的运行记录
- `GET /api/v1/neodata/token-status` — 仅 NeoData 的 token 状态(本端点的子集)
