#!/usr/bin/env bash
# 从 backend OpenAPI 生成 frontend TS 类型(对齐 CLAUDE.md §9)。
#
# 使用:
#   bash backend/scripts/gen-frontend-types.sh
#
# 行为:
#   1. 启动 backend 服务(已起则跳过)
#   2. curl /openapi.json 拉 schema
#   3. openapi-typescript 生成 frontend/lib/api-types.ts
#   4. prettier 格式化
#
# 前置:frontend/package.json 已含 devDependency openapi-typescript

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
OPENAPI_URL="http://localhost:${BACKEND_PORT}/openapi.json"
OUT="${ROOT}/frontend/lib/api-types.ts"

if [ ! -d "${ROOT}/frontend" ]; then
  echo "[gen-types] frontend/ 不存在 — frontend 还未入仓,跳过。" >&2
  exit 0
fi

# 1) 检查 backend 是否在跑
if ! curl -fsS "${OPENAPI_URL}" -o /tmp/_openapi_check.json 2>/dev/null; then
  echo "[gen-types] backend 未在 ${OPENAPI_URL} 响应。"
  echo "          先起 backend:cd backend && PYTHONPATH=../agents uv run uvicorn app.main:app --port ${BACKEND_PORT}"
  exit 1
fi

# 2) 走 frontend node_modules 内的 openapi-typescript
cd "${ROOT}/frontend"
if [ ! -f node_modules/.bin/openapi-typescript ]; then
  echo "[gen-types] 依赖未装,先 pnpm install"
  pnpm install --frozen-lockfile || pnpm install
fi

# 3) 生成
echo "[gen-types] 拉取 ${OPENAPI_URL} → ${OUT}"
mkdir -p "$(dirname "${OUT}")"
node_modules/.bin/openapi-typescript "${OPENAPI_URL}" -o "${OUT}"

# 4) 格式化(若有 prettier)
if [ -f node_modules/.bin/prettier ]; then
  node_modules/.bin/prettier --write "${OUT}"
fi

echo "[gen-types] 完成。请把变更 commit 入 PR(CI 会校验生成产物存在)。"
