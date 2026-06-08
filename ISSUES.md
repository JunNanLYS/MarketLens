# MarketLens Issues

> 审查/issue tracker：发现新问题 → 登记 → 修复 → 删除。
> 决策历史归档在 `docs/dev/issues_YYYY-MM-DD.md`（按日期归档）。

## 当前规模

- **29 张表**（SQLite，DDL 全在 `backend/storage/schema.py::TABLE_DDLS`）
- **74 端点**（68 在 `backend/api/*.py` + 2 在 `backend/main.py` + 4 `data_sources` 子路径）
- **8 个 Provider**（`backend/collectors/*.py`：NeoData / RSS / SearchEngineNews / Sina / SinaNews / TencentNews / TencentNewsHTTP / WeStock）
- **488 测试**（`pytest asyncio_mode = "auto"`；第 12 轮新增 19 个）

## 已知问题登记

> 新发现的 bug 在此处登记。**格式**：`### [严重度] \`文件:行号\` — 标题`
> 修复后从本节删除，归档到 `docs/dev/issues_<修复日期>.md`

<!-- 在此下方追加新问题 -->


## 历史归档

- `docs/dev/issues_2026-06-08.md` — 第 4-11 轮审查 70+ 条 + 9 轮修复决策历史
- `docs/dev/issues_2026-06-08_r12.md` — 第 12 轮审查 11 条 + 修复（CRITICAL 1 + MAJOR 5 + MINOR 3 + NIT 2）
