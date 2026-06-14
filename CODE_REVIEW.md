# Code Review: P0/P1/P2 Refactoring 2026-06-14

对本次重构（collection_service 拆 mixin、westock 拆 normalizers、data.py 拆子包、evidence_builder 注册表化、Settings 拆 4 块）进行全维度审查。

**2026-06-14 修复完成**：所有 12 项问题已全部修复（1 CRITICAL + 5 MAJOR + 3 MINOR + 3 NIT）。详见 git log。

---

## 修复明细

| 严重度 | 问题 | 修复方式 |
|---|---|---|
| CRITICAL | `build_multi()` 未走注册表 | 抽 `_fetch_rows_multi()` + 加 `multi_strategy` 字段 + 注册表通用调度 |
| MAJOR | `westock` 跨文件重复 `_try_number` / `_A_SHARE_PREFIXES` | 删 `westock.py` 内的两份定义，从 `westock_normalizers` import |
| MAJOR | `data/` 子包 4 份 `_get_service()` 重复 | 抽到 `_service.py`，4 子模块 import |
| MAJOR | `_build_*` wrapper 与 `_pp_*` 后处理重复 | `_build_dividends` / `_build_profit_forecasts` 委托给 `_pp_*` |
| MAJOR | `reload_providers` 绕过 `AssetService` 封装 | 给 AssetService 加 `update_providers()` 公开 API |
| MAJOR | `_save_raw_data` 模块级+实例方法二重定义 | 删实例方法包装，2 处调用改用模块级函数 |
| MAJOR | `SourceTimeoutCell` draft 丢失 + 空输入 fallback | `useEffect` 条件修正 + draft 接受 null + 禁用保存 |
| MINOR | `TasksCard` fallback query 死代码 | 移除子组件 `useQuery` 与 5 行 finalXxx 计算 |
| MINOR | `reload_providers` 共享引用无注释 | 加注释说明 `AssetService` 共享 list 引用语义 |
| MINOR | `DataSourcesStatusCard` `as` 强转 | 利用 props 类型自然收窄，删 `as` 与 dead import |
| NIT | `postprocess_kind` 缺枚举类型 | 改 `Literal[...]`，IDE 提示新增特殊项 |
| NIT | `EditableSettingsCard` 3 mutation 重复模式 | 抽 `onSettingError` 高阶函数 + `invalidateSettingQueries` helper |
