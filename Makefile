# 个人单机使用 — 一键命令清单
#
# 标准上手:
#   make setup    # 一次性:起容器 + 装依赖 + 跑 migration
#   make up       # 启所有 12 个 Python 进程(honcho)
#   make demo     # setup + up + 自动跑反诈视频 mock 端到端
#   make down     # 停容器
#   make logs     # 跟所有进程日志
#   make test     # 跑全套件
#
# 所有 docker-compose 命令默认走 mock 模式(LITELLM_MOCK=true),零 secret 即可上手。

.PHONY: setup up down demo logs test test-unit test-smoke clean help

COMPOSE := docker compose -f backend/infrastructure/docker-compose.yml -f backend/infrastructure/docker-compose.mock.yml
BACKEND_DIR := backend
AGENTS_DIR := agents

help:  ## 列出所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ────────────────────────────────────────────────────────────
# 一次性准备
# ────────────────────────────────────────────────────────────
setup: setup-env setup-infra setup-deps setup-db  ## 一次性:env / 容器 / 依赖 / 库 schema

setup-env:  ## 拷 .env.example → .env(若不存在)
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "[setup] 已生成根目录 .env(默认 LITELLM_MOCK=true,零 secret 即可跑)"; \
	else \
		echo "[setup] .env 已存在,跳过"; \
	fi

setup-infra:  ## docker-compose up 起 5 个基础容器(postgres/redis/minio/qdrant/litellm-mock)
	$(COMPOSE) up -d
	@echo "[setup] 等容器 healthy(最多 60s)..."
	@for i in $$(seq 1 60); do \
		ready=$$($(COMPOSE) ps --format json | grep -c '"Health":"healthy"' || true); \
		if [ "$$ready" -ge 3 ]; then echo "[setup] 容器 ready"; exit 0; fi; \
		sleep 1; \
	done; \
	echo "[setup] ❌ 60s 超时,以下是当前状态:"; \
	$(COMPOSE) ps; \
	exit 1

setup-deps:  ## 从根 uv.lock 安装 backend + agents + MCP workspace
	uv sync --locked --all-packages --all-extras

setup-db:  ## alembic upgrade head + canonical Skill bootstrap
	cd $(BACKEND_DIR) && uv run alembic upgrade head && uv run python scripts/bootstrap-skills.py

# ────────────────────────────────────────────────────────────
# 启停
# ────────────────────────────────────────────────────────────
_ensure-honcho:  # 内部:无 honcho 时自动装(uv tool / pip --user 兜底)
	@command -v honcho >/dev/null 2>&1 || uv tool install honcho || pip install --user honcho

up: _ensure-honcho  ## honcho start — 一键起 12 个 Python 进程
	honcho start

up-backend: _ensure-honcho  ## 只起 backend(改 backend 代码时单独重启用)
	honcho start backend

up-agents: _ensure-honcho  ## 只起 4 个 Agent worker(改 handler 时单独重启用)
	honcho start agent_text agent_document agent_image agent_av

up-mcp: _ensure-honcho  ## 只起 7 个 MCP server(改工具时单独重启用)
	honcho start mcp_search mcp_image mcp_video mcp_audio mcp_document mcp_oss mcp_publish

down:  ## docker-compose down(保留数据卷)
	$(COMPOSE) down

clean:  ## docker-compose down -v(清掉数据卷,Postgres / MinIO / Redis 全清)
	$(COMPOSE) down -v
	@echo "[clean] 数据卷已清,下次 setup 是全新环境"

logs:  ## 跟容器日志
	$(COMPOSE) logs -f --tail=100

# ────────────────────────────────────────────────────────────
# Demo / 测试
# ────────────────────────────────────────────────────────────
demo: setup  ## 零配置 mock demo:setup + 跑反诈视频 happy path(mock LLM)
	@echo "[demo] 启 12 个进程,mock 模式,反诈视频跑通就退出"
	@echo "[demo] 在另一个终端跑:make up   然后回来看产物"
	$(MAKE) demo-anti-fraud

demo-anti-fraud:  ## 触发反诈视频 mock workflow,看产物 OSS ref
	# 用 bash + pipefail,确保 python 脚本的 exit code 不被 tail 吞掉
	# (否则反诈 demo 失败时 make 仍报成功,屏蔽真实问题)
	@bash -c 'set -o pipefail; cd $(BACKEND_DIR) && \
		LITELLM_MOCK=true \
		YOULE_AUTO_APPROVE_HITL=true \
		uv run python ../../test/run_anti_fraud_video_real_workflow.py 2>&1 | tail -30' || \
		{ echo "[demo] ❌ 反诈视频失败 — 先确认 make up 在跑;脚本默认 LITELLM_MOCK=false 已被本 target 覆盖"; exit 1; }

test: test-unit test-smoke  ## 跑全测试

test-unit:  ## 单测(200 用例)
	cd $(BACKEND_DIR) && uv run pytest tests/unit -q

test-smoke:  ## smoke(连 db/redis/minio)
	cd $(BACKEND_DIR) && uv run pytest tests/smoke -q

# ────────────────────────────────────────────────────────────
# 调试辅助
# ────────────────────────────────────────────────────────────
ps:  ## 看容器状态
	$(COMPOSE) ps

shell-db:  ## 进 postgres
	$(COMPOSE) exec postgres psql -U youle -d youle

shell-redis:  ## 进 redis-cli
	$(COMPOSE) exec redis redis-cli

minio-console:  ## 打开 minio 控制台 URL
	@echo "MinIO 控制台: http://localhost:9001 (账号: minioadmin / minioadmin)"

# ────────────────────────────────────────────────────────────
# 健康检查 — 一眼看 12 进程 + 5 容器谁好谁不好
# ────────────────────────────────────────────────────────────
doctor:  ## 健康检查:容器 / backend / Agent / MCP / 端口全扫一遍
	@echo "═══════════════════════════════════════════════════════"
	@echo " youle 健康检查"
	@echo "═══════════════════════════════════════════════════════"
	@echo ""
	@echo "[1] 基础设施容器 ─────────────────────────"
	@$(COMPOSE) ps --format "table {{.Service}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || echo "  ❌ docker-compose 未起,跑 make setup-infra"
	@echo ""
	@echo "[2] 后端 backend ────────────────────────"
	@curl -fsS http://localhost:8000/ready 2>/dev/null | sed 's/^/  ✓ /' || echo "  ❌ backend 没在 :8000 响应,检查 honcho 的 backend.1 日志"
	@echo ""
	@echo "[3] Agent 心跳(Redis agent_status:* keys)────"
	@$(COMPOSE) exec -T redis redis-cli --scan --pattern 'agent_status:*' 2>/dev/null | sort | sed 's/^/  ✓ /' || echo "  ❌ 无法连 redis,容器可能没起"
	@echo "  (期望:agent_status:agent_1/2/3/4 各一行)"
	@echo ""
	@echo "[4] 端口监听 ──────────────────────────"
	@# /dev/tcp 是 bash-only(dash/sh 不支持),显式用 bash;
	@# 没 bash 时 fallback 到 nc / curl 任一可用工具。
	@for port in 8000 5432 6379 9000 9001 6333 4000; do \
		if bash -c "exec 3<>/dev/tcp/localhost/$$port" 2>/dev/null; then \
			echo "  ✓ :$$port  开放"; \
		elif command -v nc >/dev/null 2>&1 && nc -z localhost $$port 2>/dev/null; then \
			echo "  ✓ :$$port  开放"; \
		else \
			echo "  ❌ :$$port  无响应"; \
		fi; \
	done
	@echo ""
	@echo "[5] honcho 进程数量(若用 make up 启动)────"
	@PIDS=$$(pgrep -f "honcho start" || true); \
	if [ -n "$$PIDS" ]; then \
		echo "  ✓ honcho 在跑(pid $$PIDS)"; \
		PYTHON_COUNT=$$(pgrep -fc "uv run python -m" || echo 0); \
		echo "  ✓ Python 子进程数: $$PYTHON_COUNT  (期望: 11 = 4 Agent + 7 MCP)"; \
	else \
		echo "  ⚠️  honcho 未跑;若用 docker / 别的方式启动,无视此项"; \
	fi
	@echo ""
	@echo "═══════════════════════════════════════════════════════"
	@echo " 任意 ❌ → 看上方提示;✓ 全绿 → 可以跑 make demo-anti-fraud"
	@echo "═══════════════════════════════════════════════════════"
