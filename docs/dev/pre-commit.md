# pre-commit 钩子使用指南

本项目使用 [pre-commit](https://pre-commit.com/) 在提交/推送前自动检查代码质量。配置文件位于
[`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)。

## 钩子清单

`.pre-commit-config.yaml` 注册了 3 类钩子源：

| 钩子 ID | 触发阶段 | 作用 |
| --- | --- | --- |
| `trailing-whitespace` | pre-commit | 删除行尾空白 |
| `end-of-file-fixer` | pre-commit | 补齐文件末尾换行 |
| `check-yaml` | pre-commit | YAML 语法校验 |
| `check-toml` | pre-commit | TOML 语法校验 |
| `ruff` (legacy alias) | pre-commit | ruff lint + `--fix` 自动修复 |
| `ruff-format` | pre-commit | ruff 格式化（与 `pyproject.toml` 锁定的 ruff>=0.15.16 对齐） |
| `pytest-fast` | **pre-push** | 跑 `uv run pytest tests/ -x -q`，首个失败即停 |

> **重要**：`pytest-fast` 只在 `pre-push` 阶段触发（见 `stages: [pre-push]`），
> 单个 `git commit` 不会跑测试。这是有意为之——提交阶段只做格式校验，完整测试放到推送前。

## 当前状态：未自动安装 Git Hook

截至本文档创建时，`.pre-commit-config.yaml` 已落入仓库，但 `.git/hooks/` 目录**没有**生成
`pre-commit` / `pre-push` 可执行钩子。原因：

- 本项目使用 `uv` 管理 Python 依赖，**没有把 `pre-commit` 加入 `pyproject.toml` 的
  `dependency-groups`** —— 避免所有克隆本仓库的开发者在 `uv sync` 时被迫安装它。
- 钩子的实际执行依赖 `uv` 路径下的 Python + 预下载的钩子环境（首次运行约 14s 拉取 virtualenv），
  对单用户本地工具属于"按需启用"而非"开箱即用"。

**结论**：当前提交/推送**不会**自动触发钩子；需要开发者**手动**安装一次。

## 手动安装

如需启用提交/推送自动门禁：

```bash
# 1. 全局安装 pre-commit（也可选 uv tool 方式）
uv tool install pre-commit
# 或：pipx install pre-commit

# 2. 在仓库根目录执行 install
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

> `--hook-type pre-push` 必须显式声明——默认 `pre-commit install` 只装 `pre-commit` 阶段，
> `pytest-fast` 钩子（`stages: [pre-push]`）不会生效。

安装后验证：

```bash
ls .git/hooks/pre-commit .git/hooks/pre-push    # 两个文件均应存在
```

## 手动跑全部钩子（无需 install）

不安装 git 钩子也能在命令行手动跑：

```bash
# 用 uv tool 临时跑（首次会下载 virtualenv + 钩子环境，~14s；之后秒级）
uv tool run pre-commit run --all-files

# 仅跑特定钩子
uv tool run pre-commit run --all-files --hook trailing-whitespace
uv tool run pre-commit run --all-files --hook end-of-file-fixer
uv tool run pre-commit run --all-files --hook ruff
uv tool run pre-commit run --all-files --hook ruff-format

# 仅跑 pre-push 阶段（包含 pytest-fast）
uv tool run pre-commit run --all-files --hook-stage pre-push
```

> **注意**：`pre-commit run --all-files` 默认只跑 `pre-commit` 阶段的钩子；
> 测 `pytest-fast` 必须显式 `--hook-stage pre-push`。

## 第 12 轮首次验证记录

2026-06-08 第 12 轮（Sub Agent 1）首次跑 `pre-commit run --all-files` 时发现仓库存在
历史遗留格式问题，钩子自动修复了以下内容：

- **29 个文件** `end-of-file-fixer`：补齐缺失的 EOF 换行（如 `backend/scheduler/jobs.py`、
  `ui/api_client.py`、`docs/features.md`、`config.yaml` 等）。
- **72 个文件** `ruff-format`：主要是字典/列表的多行折行（与 `pyproject.toml` 锁定的
  ruff>=0.15.16 行为差异），同时 `backend/api/data.py` 等文件移除了文件头 BOM。
- 合计 **78 个文件，+3051/-1112 行**改动；二次运行所有钩子全部 Passed。

修复后 `uv run ruff check .` 也保持 `All checks passed!`。

> 上述改动**未提交**——留给后续批次按"质量门禁"类提交统一处理。
> 如需回滚：`git restore .` 即可（pre-commit 钩子只对工作区做修补，不动 git 索引）。

## 故障排查

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| `pre-commit: command not found` | 未安装 | `uv tool install pre-commit` |
| `ruff: command not found` | 钩子环境未下载 | `uv tool run pre-commit run --all-files` 触发下载 |
| `pytest-fast` 不触发 | 未装 pre-push 钩子 | `pre-commit install --hook-type pre-push` |
| 提交时钩子失败 | 格式未通过 | 按终端提示 `git add` 修复后的文件后重新 `git commit` |
| 想跳过钩子（紧急情况） | — | `git commit --no-verify`（不推荐） |
