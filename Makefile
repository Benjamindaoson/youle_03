.PHONY: setup infra-up infra-down migrate up backend agent frontend test check

COMPOSE := docker compose -f compose.core.yml

setup: infra-up
	uv sync --locked --all-packages --all-extras
	pnpm --dir frontend install --frozen-lockfile
	$(MAKE) migrate

infra-up:
	$(COMPOSE) up -d --wait

infra-down:
	$(COMPOSE) down

migrate:
	cd backend && uv run alembic upgrade head && uv run python scripts/bootstrap-skills.py

up:
	LITELLM_MOCK=true uvx honcho start

backend:
	cd backend && LITELLM_MOCK=true uv run python -m app.run --host 127.0.0.1 --port 8000

agent:
	LITELLM_MOCK=true uv run python -m agents.core_worker

frontend:
	pnpm --dir frontend dev

test:
	uv run pytest backend/tests/unit -q
	uv run pytest agents/tests/unit -q
	pnpm --dir frontend test

check:
	uv run ruff check backend agents
	pnpm --dir frontend typecheck
	pnpm --dir frontend lint
	pnpm --dir frontend build
