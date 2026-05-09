# 个人单机一键启动:`uvx honcho start`(或 `make up`)
#
# 12 个进程 + 容器化的基础设施(postgres / redis / minio / qdrant / litellm-mock)
# 由 docker-compose 管,本文件只管 Python 应用层。
#
# 启动顺序:honcho 并发起所有进程,但 backend 会等 alembic 跑完(由它自己保证 db ready)
# Agent / MCP 进程依赖 backend + redis,redis 在 docker 里已 healthy 才会 honcho start。
#
# 日志:honcho 自动按 process_name 着色 + 行前缀,跟踪某个 Agent 看 prefix 即可。
# Ctrl+C:honcho 会向所有子进程发 SIGTERM,优雅清理。
# 单进程重启:honcho start backend(只启 backend);其他进程不动。

# ── 主后端 ──
backend:    cd backend && PYTHONPATH=../agents uv run uvicorn app.main:app --port 8000 --reload

# ── 4 个 Agent worker(铁律 #2:1=text/2=document/3=image/4=av),包名 agents.* ──
agent_text:     cd agents && uv run python -m agents.text_agent.main
agent_document: cd agents && uv run python -m agents.document_agent.main
agent_image:    cd agents && uv run python -m agents.image_agent.main
agent_av:       cd agents && uv run python -m agents.av_agent.main

# ── 7 个 MCP server(铁律 #13:工具走 MCP)──
mcp_search:    cd agents/mcp_servers && uv run python -m search.server
mcp_image:     cd agents/mcp_servers && uv run python -m image_tools.server
mcp_video:     cd agents/mcp_servers && uv run python -m video_tools.server
mcp_audio:     cd agents/mcp_servers && uv run python -m audio_tools.server
mcp_document:  cd agents/mcp_servers && uv run python -m document_tools.server
mcp_oss:       cd agents/mcp_servers && uv run python -m oss.server
mcp_publish:   cd agents/mcp_servers && uv run python -m platform_publish.server

# ── 前端 ──
# frontend: cd frontend && pnpm dev
