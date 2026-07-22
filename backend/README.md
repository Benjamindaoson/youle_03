# Backend

## 起步

在项目**仓库根目录**准备 `.env` 后：

```bash
cd backend && uv sync
# （根目录已有 .env.example 时）
# cp ../.env.example ../.env

# 启基础设施 — 须在仓库根执行，或改用 -f 绝对路径
docker compose -f deploy/production/docker-compose.yml \
  -f deploy/production/docker-compose.mock.yml up -d

cd backend && uv run alembic upgrade head

# 主编排 Python 包在 ../agents/agents ; pytest/mypy 已在 pyproject 配置了 pythonpath
export PYTHONPATH="../agents${PYTHONPATH:+:$PYTHONPATH}"
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# PowerShell: $env:PYTHONPATH = "..\\agents;" + $env:PYTHONPATH
```

## 测试

```bash
cd backend
uv run pytest tests/smoke/ -v       # Sprint 0 健康检查
uv run pytest                       # 全套
uv run ruff check .
uv run mypy app/
```

## 目录结构

见 `docs/ARCHITECTURE.md §1`。

## 铁律

代码需符合仓库根目录 `CLAUDE.md` 的约束；CI 会跑黑名单 grep。
