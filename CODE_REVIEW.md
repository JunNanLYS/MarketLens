# MarketLens Code Review

审查日期：2026-05-31
审查范围：全部 P0 后端 + UI 代码
审查方法：三轮审查（架构 → 逐文件 → 边界加固）

---

## [MINOR] 可维护性问题（未修复）

### m-1: API 层服务实例在模块加载时创建

**文件**: [assets.py](file:///d:/Project/MarketLens/backend/api/assets.py), [data.py](file:///d:/Project/MarketLens/backend/api/data.py), [news.py](file:///d:/Project/MarketLens/backend/api/news.py), [reports.py](file:///d:/Project/MarketLens/backend/api/reports.py), [portfolio.py](file:///d:/Project/MarketLens/backend/api/portfolio.py)

```python
_service = AssetService()
```

所有 API 路由模块在模块加载时创建服务实例，这意味着：
1. 应用启动时就会触发 Provider 初始化和 config 加载
2. 测试时无法轻松替换服务实例
3. 每个路由模块创建独立的服务实例，Provider 也被重复创建

**建议**: 使用 FastAPI 依赖注入（`Depends`）管理服务生命周期，或使用 `functools.lru_cache` 确保单例。

**状态**: 未修复 — 涉及所有路由文件，改动面广，建议作为独立重构任务处理。

---

## 已修复问题

以下问题已在 2026-05-31 的修复提交中解决：

| 编号 | 严重级别 | 问题 | 修复方式 |
|------|---------|------|---------|
| C-1 | CRITICAL | LIKE 通配符未转义（asset_service.py） | 添加 `_escape_like` 函数 + `ESCAPE '\\'` 子句 |
| C-2 | CRITICAL | LIKE 通配符未转义（news_service.py） | 添加 `_escape_like` 函数 + `ESCAPE '\\'` 子句 |
| C-3 | CRITICAL | `_match_symbols` 子字符串匹配过于宽泛 | 改用正则 `(?<![a-zA-Z0-9])...(?![a-zA-Z0-9])` 精确匹配 |
| M-1 | MAJOR | 持仓计算未按时间排序 | SQL 添加 `ORDER BY trade_date, created_at` |
| M-2 | MAJOR | 重复方法 `_get_current_holding` | 删除未使用的方法 |
| M-3 | MAJOR | `affected_assets` 只记录成功数 | 改为记录总数 |
| M-4 | MAJOR | 新闻采集每条新闻独立数据库连接 | 合并为单个 `with get_db()` 上下文 |
| M-5 | MAJOR | `_collect_data_sources` 重复查询 6 次数据库 | `_build_*` 方法附带 `_source`/`_collected_at`，改为纯内存操作 |
| M-6 | MAJOR | 资金流连续判断统计历史最长而非最近 | 改为从最近日期开始计数，遇异向即停止 |
| m-2 | MINOR | 错误响应格式不一致 | 自定义 `HTTPException` 处理器，dict 直接展开 |
| m-3 | MINOR | 行情采集重复代码 | 提取 `_collect_quote_for_symbol` 公共方法 |
| m-4 | MINOR | 持仓计算重复代码 | 提取 `_compute_position_detail` 静态方法 |
| m-5 | MINOR | 调度描述硬编码 | 改为从 config 动态生成 |
| m-6 | MINOR | UI 健康检查频率过高 | 添加 30s TTL 缓存 |
| n-1 | NIT | `Optional[X]` 混用 | 统一为 `X | None` |
| n-2 | NIT | Pydantic 模型类型注解不一致 | 统一为 `X | None` |

---

## 审查总结

| 严重级别 | 发现数 | 已修复 | 未修复 |
|----------|--------|--------|--------|
| CRITICAL | 3 | 3 | 0 |
| MAJOR | 6 | 6 | 0 |
| MINOR | 6 | 5 | 1 |
| NIT | 2 | 2 | 0 |
| **合计** | **17** | **16** | **1** |
