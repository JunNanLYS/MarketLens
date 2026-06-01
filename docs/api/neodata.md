# NeoData Token 管理 API

> 资源路径: `/api/v1/neodata` | 接口数: 2

---

## GET /token-status

查看 NeoData 凭证的当前状态，不暴露 token 原文。

**响应示例**:

```json
{
  "has_token": true,
  "source": "cache",
  "expires_at": "2027-04-15T12:00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `has_token` | bool | 是否有可用凭证 |
| `source` | string | `cache` / `config` / `env` / `none` |
| `expires_at` | string \| null | 过期时间（ISO 8601），JWT 读取 `exp`，tempToken 读取 `saved_at + 12h` |

---

## POST /token

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

**错误响应** (422):

当 `token` 为空字符串时返回 Pydantic 校验错误。
