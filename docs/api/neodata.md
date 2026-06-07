# NeoData Token 管理 API

> 资源路径: `/api/v1/neodata` | 接口数: 2

---

## 鉴权

| 方法 | 是否需要 API Key |
|---|---|
| `GET /token-status` | 否 |
| `POST /token` | 是（需 `X-API-Key` 头） |

API Key 来源：环境变量 `MARKETLENS_API_KEY` > `config.security.api_key`，本地默认 `marketlens-local`。缺失或错误时返回 `401 UNAUTHORIZED`。

---

### `GET /token-status`

查看 NeoData 凭证的当前状态，不暴露 token 原文。

**响应示例**:

```json
{
  "is_valid": true,
  "source": "cache"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_valid` | bool | 是否有可用凭证（由后端从 token 解析/验证后返回，不暴露原文及过期时间） |
| `source` | string \| null | token 来源：`cache` / `config` / `env` / `none` |

---

### `POST /token`

保存 NeoData 凭证到本地缓存文件 `~/.workbuddy/.neodata_token`。

**请求体**:

```json
{
  "token": "<凭证字符串>"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `token` | string | 是 | 凭证内容，非空 |

**响应** (200):

```json
{"message": "Token saved successfully"}
```

**错误响应** (401):

缺失或错误的 `X-API-Key`：

```json
{ "error": "UNAUTHORIZED", "detail": "无效或缺失的 API Key" }
```

**错误响应** (422):

当 `token` 为空字符串时返回 Pydantic 校验错误。
