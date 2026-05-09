#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 未安装，请先安装 Python 3.12+" >&2
  exit 1
fi

python3 - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit("需要 Python 3.12+")
PY

if ! command -v uv >/dev/null 2>&1; then
  echo "uv 未安装，请先安装 uv" >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 .env"
else
  echo "保留现有 .env"
fi

echo "▸ 创建根目录 .venv..."
uv venv .venv --python "$(command -v python3)"

echo "▸ 安装 backend 依赖..."
uv pip install --python .venv/bin/python -e "./backend[dev]"

echo "▸ 安装 agents 依赖..."
uv pip install --python .venv/bin/python -e "./agents[dev]"

echo "▸ 安装 mcp_servers 依赖..."
uv pip install --python .venv/bin/python -e "./agents/mcp_servers"

echo ""
echo "Python 环境已就绪。"
echo "激活命令: source .venv/bin/activate"
echo "后端启动示例:"
echo "  env -u DEBUG .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

if ! command -v docker >/dev/null 2>&1; then
  echo ""
  echo "提示: 当前 shell 没有 docker，数据库/Redis/MinIO/Qdrant 暂时无法用 docker compose 启动。"
fi
