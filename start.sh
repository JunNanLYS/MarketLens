#!/usr/bin/env bash
# MarketLens 一键启动前后端
# ./start.sh  或  bash start.sh
# 拉起 FastAPI (8000) + Streamlit (8501) + 自动弹浏览器
# Ctrl+C 优雅清理子进程

set -e

# 切到脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "MarketLens 启动中..."

if ! command -v uv >/dev/null 2>&1; then
    echo "错误: uv 未安装"
    echo "  安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  或参考: https://docs.astral.sh/uv/"
    exit 1
fi

uv run python scripts/launcher.py
