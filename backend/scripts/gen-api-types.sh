#!/usr/bin/env bash
# 生成前端 ts 类型(后端 OpenAPI → frontend/lib/api-types.ts)
set -euo pipefail
cd "$(dirname "$0")/.."

API_URL="${API_URL:-http://localhost:8000}"
echo "Fetching OpenAPI from $API_URL ..."

cd frontend
pnpm exec openapi-typescript "$API_URL/openapi.json" -o lib/api-types.ts
echo "✓ frontend/lib/api-types.ts updated"
