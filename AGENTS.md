# AGENTS.md — MarketLens 金融研究助理系统

## 1. 项目概述

MarketLens 是一个本地优先的 AI 金融研究助理。技术栈：Python + FastAPI（后端）、SQLite（数据库）、APScheduler（调度）、pandas（数据处理）、Streamlit（UI）。

## 2. 目录与模块边界

```
backend/collectors/  → 数据采集提供者（仅此可调外部数据源）
backend/services/    → 业务逻辑（追踪标的、证据构建）
backend/storage/     → 数据库读写与初始化
backend/scheduler/   → 定时任务注册
ui/                  → Streamlit 页面（不应直接访问 DB）
tests/               → 必须镜像 backend/ 目录结构
```

- `ui/` 不直接读数据库，通过 FastAPI 接口获取数据。
- 新增数据源只在 `backend/collectors/` 下创建，遵循统一接口。

## 3. 环境与包管理

- **系统依赖：Node.js ≥ v18**（`westock-data-clawhub` CLI 运行所需）。
- **必须使用项目虚拟环境 Python**，不得依赖系统全局 Python。
- **使用 `uv` 进行包管理**（安装依赖、锁定版本、运行脚本）。
- **Python 版本要求 ≥ 3.13**。
- 依赖列表维护于 `pyproject.toml`，由 `uv` 统一管理。

## 4. 数据源提供者模式

- **声明与实现分离**：`config.yaml` 只管"有什么源、优先顺序、连接参数"；具体获取逻辑由 `backend/collectors/` 下的 Provider 类实现，`config.yaml` 中 `provider` 字段指明类名。
- 通用获取模式（如 RSS HTTP GET）应抽象为通用 Provider，通过 `params` 复用，避免每个源写重复代码。
- 数据源列表及优先级由 `config.yaml` 中 `data_sources` 的顺序决定，**代码中不得硬编码数据源名称或优先级**。
- 所有提供者实现统一接口：`search()` / `quote()` / `kline()` / `finance()` / `fund_flow()` / `technical()`。
- 每次采集须同时保存**原始返回**和**标准化数据**（可追溯原则）。
- 数据源失败**不得**引发系统崩溃——捕获异常、记入 `run_logs`、继续下一个标的。
- 标记为 `optional: true` 的源不可用时静默跳过，不阻塞主流程。

## 5. AI 证据优先（核心原则）

- AI 分析**禁止凭空生成**，必须从数据库读取行情、资金、财务、新闻证据。
- 新增 AI 分析逻辑前，必须通过 `EvidenceBuilder` 组装证据包。
- 输出字段必须包含 `data_used` 列出所引用的数据源。
- 输出 JSON schema（action / confidence / risk_level / summary / reasons / key_risks）不可擅自增删字段。

## 6. 数据库变更

- 所有 schema 变更集中于 `backend/storage/` 的初始化脚本。
- 禁止在业务代码中直接执行 `ALTER TABLE` 或 `CREATE TABLE`。
- 新增表后同步更新核心表清单。
- SQLite 为唯一数据库，不要引入其他数据库依赖。

## 7. API 设计（RESTful 规范）

> **使用技能：`restful-api-design`** — 设计、修改或评审 API 时必须调用此技能，遵循其规范。

- 所有 API 遵循 RESTful 约定：资源用名词复数、HTTP 方法语义正确、路径层级清晰。
- 标准方法映射：
  - `GET /resources` — 列表查询（支持分页、筛选、排序）
  - `GET /resources/{id}` — 单资源详情
  - `POST /resources` — 创建资源
  - `PATCH /resources/{id}` — 部分更新
  - `DELETE /resources/{id}` — 删除资源
- 错误响应统一格式：`{"error": "错误码", "detail": "详细描述"}`。
- 使用合适的 HTTP 状态码（200 / 201 / 400 / 404 / 422 / 500）。
- URL 使用小写连字符（kebab-case），不用驼峰或下划线。

## 8. 调度任务

- 所有定时任务通过 `APScheduler` 注册，不另建定时机制。
- 每个任务必须：指定频率、写入 `run_logs`（成功/失败/耗时/错误）。
- 任务必须幂等——重复执行不产生重复数据。
- 默认任务频率：行情 15min、K 线/资金/技术日收盘后、新闻每小时、AI 报告每晚。

## 9. 日志与可观测性

- **使用 `loguru` 进行日志记录**，替代标准库 `logging`。
- 数据采集、AI 分析、调度触发必须在 `run_logs` 表中留下记录。
- 字段：`task_name` / `status` / `started_at` / `finished_at` / `error_message` / `affected_assets`。
- `loguru` 用于本地调试与文件日志，`run_logs` 用于运行期持久化追踪。

## 10. 配置管理

- 所有可配参数集中于 `config.yaml`，代码启动时加载。
- 数据源、数据库路径、超时、调度频率、AI 阈值等均从配置文件读取。
- 禁止在代码中硬编码路径、密钥、超时值。
- 新增配置项必须提供合理默认值。

## 11. 错误处理

- FastAPI 异常统一返回 `{"error": "...", "detail": "..."}` 格式。
- 外部调用（subprocess、HTTP）均需设置超时并捕获异常。
- 单个标的采集失败不影响其他标的。

## 12. 代码风格

> **使用技能：`Python 类型注解`** — 编写或修改 Python 代码时必须调用此技能，确保类型注解完整且符合项目规范。

- 必须使用 Python 类型注解（函数签名、类属性）。
- 数据处理优先用 `pandas`，文件路径用 `pathlib`。
- 导入顺序：标准库 → 第三方 → 本地模块。
- 所有注释和文档字符串用中文（与现有文档保持一致）。
- 遵守 PEP8 规范

## 13. 任务收尾检查清单

**在每项任务结束前，必须按以下顺序执行检查：**

1. **代码报错检查** — 检查本次修改涉及的代码是否存在语法错误或可静态检测的逻辑问题。若有报错，立即修复，修复完成后重新从第 1 步开始执行本清单。

2. **测试判断与执行** — 判断本次任务修改是否属于以下需要测试的范畴：
   - 新增或修改 `backend/` 下的业务逻辑代码；
   - 新增或修改 API 接口（`backend/` 路由、服务层）；
   - 修改数据库 schema 或存储层代码。
   若属于上述范畴，则运行相关测试（`uv run pytest tests/` 或对应测试文件），确保所有测试通过。

3. **文档同步** — 当本次任务对后端 API 进行了新增、修改或删除操作后，必须同步更新 `docs/api/` 目录下对应的 API 文档，确保接口路径、参数、响应格式与代码一致。同时检查 `docs/prd.md`、`docs/features.md`、`docs/architecture.md` 是否需要联动更新。
