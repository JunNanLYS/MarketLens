# MarketLens Code Review

审查日期：2026-06-02（针对新闻采集能力修复的 3 轮提交进行审查）
审查范围：21ed12e..b440f5e（rss.py, sina_news.py, tencent_news_http.py, tencent_news.py, westock.py, __init__.py, config.yaml）
审查方法：三轮审查 + 代码审查技能维度检查

---

## 本次审查发现的新问题

### [MAJOR] N-31: RSSProvider._get_text 在 rewrite 过程中丢失 @staticmethod

- **File:** backend/collectors/rss.py:148
- **Problem:** 在 rss.py 的 feedparser 集成 rewrite 过程中，`_get_text` 方法意外地变为模块级函数（丢失了 `@staticmethod` 装饰器和类内缩进）。虽然当前 feedparser 作为主解析器覆盖了所有 RSS 源，但 `_parse_with_etree` 回退路径会触发 `AttributeError`。
- **Fix:** 已恢复 `_get_text` 为类内 `@staticmethod`。
- **Status:** ✅ 已修复

### [MAJOR] N-32: __init__.py create_providers 丢失类型注解和中文字符串

- **File:** backend/collectors/__init__.py:24-47
- **Problem:** 在 rewrite 过程中丢失了参数/返回值类型注解、中文文档字符串、中文日志消息，且函数内部冗余 `from loguru import logger`。
- **Violation:** AGENTS.md §11 — type annotations; AGENTS.md §11 — Chinese comments
- **Fix:** 已恢复完整的类型注解、中文文档字符串、中文日志消息，移除冗余导入。
- **Status:** ✅ 已修复

### [MINOR] N-33: tencent_news.py _max_items 条件多余

- **File:** backend/collectors/tencent_news.py:23
- **Problem:** `int(params.get("max_items", 50)) if (params and "max_items" in params) else 50` 中 `"max_items" in params` 是多余的——dict.get() 本身就会在 key 不存在时返回默认值。
- **Fix:** 已简化回原写法，并补充类型注解 `_max_items: int`。
- **Status:** ✅ 已修复

### [MINOR] N-34: 新 Provider 缺少重复类型注解

- **File:** backend/collectors/sina_news.py:33-49, backend/collectors/tencent_news_http.py:35-51
- **Problem:** search/quote/kline/finance/fund_flow/technical 覆盖基类方法但没有重复声明类型注解。基类有注解但 AGENTS.md §11 推荐显式标注。
- **Status:** 非阻塞（基类已有注解，可后续补充）

---

## 本次修改对已有问题的影响

| 编号 | 级别 | 问题 | 处理 |
|------|------|------|------|
| N-11 | MAJOR | RSS namespace 解析失败 | feedparser 作为主解析器，etree 降为回退 |
| M-13 | MINOR | westock shell=True | 代码使用 shell=False，已排除 |
| N-28 | MAJOR | TokenManager JWT exp | 已修复 |
| N-29 | MINOR | NeoData dead code | 已修复 |
| N-30 | MINOR | NeoData docs missing | 已修复 |
| N-20 | MAJOR | NeoDataProvider type annotations | 已修复 |

---

## 新闻采集架构审查

### 安全性
- ✅ 无敏感数据硬编码
- ✅ 外部 API 调用均有超时设置
- ✅ 所有 HTTP 异常均有捕获

### 正确性
- ✅ 返回值始终为 `list[dict]`
- ✅ 时间戳处理使用 UTC，带 fallback
- ✅ 新 Provider 均为 optional，失败不阻塞主流程

### 测试覆盖
- ⚠️ 新 Provider 无单元测试（274 个已有测试全部通过）

---

## 审查总结

| 严重级别 | 本次发现 | 本次已修复 | 仍存 |
|---------|---------|-----------|------|
| CRITICAL | 0 | 0 | 0 |
| MAJOR | 2 | 2 | 0 |
| MINOR | 2 | 1 | 1 (N-34) |
| NIT | 0 | 0 | 0 |
| **合计** | **4** | **3** | **1** |

### 历史未修复问题（关键项）

| 优先 | 编号 | 问题 |
|------|------|------|
| 1 | N-9 | get_realized_pnl 会计逻辑错误 |
| 2 | N-8 | add_asset 竞态条件 |
| 3 | N-10 | LIKE 查询匹配 JSON 数组子串 |
| 4 | M-8+M-9 | EvidenceBuilder/ReportService 连接过多 |
| 5 | N-22 | tasks.py API 层直接操作数据库 |
| 6 | N-21 | evidence_builder 魔法数字硬编码 |
