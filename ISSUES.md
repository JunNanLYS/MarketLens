# MarketLens Issues

> 审查/issue tracker：发现新问题 → 登记 → 修复 → 删除。
> 决策历史归档在 `docs/dev/issues_YYYY-MM-DD.md`（按日期归档）。

## 当前规模

- **29 张表**（SQLite，DDL 全在 `backend/storage/schema.py::TABLE_DDLS`）
- **74 端点**（68 在 `backend/api/*.py` + 2 在 `backend/main.py` + 4 `data_sources` 子路径）
- **8 个 Provider**（`backend/collectors/*.py`：NeoData / RSS / SearchEngineNews / Sina / SinaNews / TencentNews / WeStock）
- **495 测试**（`pytest asyncio_mode = "auto"`；第 13 轮新增 2 个迁移测试 + 1 个 lifespan 测试）

## 已知问题登记

> 新发现的 bug 在此处登记。**格式**：`### [严重度] \`文件:行号\` — 标题`
> 修复后从本节删除，归档到 `docs/dev/issues_<修复日期>.md`

（当前无活跃问题）

## 历史归档

- `docs/dev/issues_2026-06-08.md` — 第 4-11 轮审查 70+ 条 + 9 轮修复决策历史
- `docs/dev/issues_2026-06-08_r12.md` — 第 12 轮审查 11 条 + 修复（CRITICAL 1 + MAJOR 5 + MINOR 3 + NIT 2）
- `docs/dev/issues_2026-06-11_r13.md` — 第 13 轮 React 迁移审查 27 条全部修复（CRITICAL 2 + MAJOR 13 + MINOR 7 + NIT 4 + 补充 MAJOR 1）
- `docs/dev/issues_2026-06-11_r14.md` — 第 14 轮前端审查 6 条全部修复（MAJOR 2 + MINOR 3 + NIT 1）