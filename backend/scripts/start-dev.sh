#!/usr/bin/env bash
# 一键起 dev:基础设施 + 后端 + 4 个 Agent + 7 个 MCP server + 前端
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "▸ docker compose up..."
docker compose -f backend/infrastructure/docker-compose.yml \
  -f backend/infrastructure/docker-compose.mock.yml up -d

echo "▸ alembic upgrade head..."
(cd backend && uv run alembic upgrade head)

echo ""
echo "已启动基础设施。各服务在不同终端启动:"
echo ""
echo "  # 后端(需主编排包 agents.*)"
echo "  cd backend && PYTHONPATH=../agents uv run uvicorn app.main:app --reload --port 8000"
echo ""
echo "  # Agents(4 个,各开一个终端)"
echo "  cd agents && uv run python -m agents.text_agent.main"
echo "  cd agents && uv run python -m agents.document_agent.main"
echo "  cd agents && uv run python -m agents.image_agent.main"
echo "  cd agents && uv run python -m agents.av_agent.main"
echo ""
echo "  # MCP servers(7 个)"
echo "  cd agents/mcp_servers && uv run python -m search.server"
echo "  ... (image_tools/video_tools/audio_tools/document_tools/oss/platform_publish)"
echo ""
echo "  # 前端"
echo "  cd frontend && pnpm dev"
