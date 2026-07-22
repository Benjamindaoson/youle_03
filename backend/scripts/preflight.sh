#!/usr/bin/env bash
# Sprint 6 上线预检清单(铁律 §7:跑生产命令必须问 + 二次确认)
# 用法: bash scripts/preflight.sh [staging|prod]
#
# 退出码:
#   0  全绿
#   1  阻塞:必须修
#   2  警告:可上线但有遗留风险

set -uo pipefail
ENV="${1:-staging}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; WARN_COUNT=$((WARN_COUNT+1)); }
err()  { echo -e "${RED}✗${NC} $1"; ERR_COUNT=$((ERR_COUNT+1)); }

ERR_COUNT=0
WARN_COUNT=0

echo "═══════════════════════════════════════════"
echo "  「haole」上线预检 — 环境: ${ENV}"
echo "═══════════════════════════════════════════"

# ── 1. 必需 secret(prod / staging 全要)──
echo ""
echo "[1/8] Secrets / 凭证"
required_secrets=(
  "DATABASE_URL"
  "REDIS_URL"
  "JWT_SECRET"
  "OSS_ACCESS_KEY"
  "OSS_SECRET_KEY"
  "OSS_ENDPOINT"
  "OSS_BUCKET"
  "LITELLM_URL"
  "LITELLM_MASTER_KEY"
)
[[ "$ENV" == "prod" ]] && required_secrets+=(
  "TAVILY_API_KEY"
  "VOLCENGINE_TTS_APPID"
  "VOLCENGINE_TTS_TOKEN"
  "ALIYUN_OSS_ACCESS_KEY_ID"
  "ALIYUN_OSS_ACCESS_KEY_SECRET"
  "SENTRY_DSN"
)
for s in "${required_secrets[@]}"; do
  val="${!s:-}"
  if [[ -z "$val" ]]; then
    err "缺 ${s}"
  else
    ok "${s} 已设(${#val} 字符)"
  fi
done

# ── 2. mock 残留检查(prod 不能带 mock)──
echo ""
echo "[2/8] Mock 残留(prod 必须切真 API)"
if [[ "$ENV" == "prod" ]]; then
  if [[ "${LITELLM_MOCK:-false}" == "true" ]]; then
    err "LITELLM_MOCK=true 不能进 prod"
  else
    ok "LITELLM_MOCK 未启用"
  fi
  if [[ "${USE_MOCK:-false}" == "true" ]]; then
    err "USE_MOCK=true 不能进 prod"
  else
    ok "USE_MOCK 未启用"
  fi
else
  ok "staging 允许 mock fallback"
fi

# ── 3. DB 迁移到位 ──
echo ""
echo "[3/8] Alembic 迁移"
if command -v uv >/dev/null 2>&1; then
  pushd "${ROOT}/backend" >/dev/null
  current_raw=$(uv run alembic current 2>&1 || true)
  head_raw=$(uv run alembic heads 2>&1 | tail -1 || true)
  popd >/dev/null
  # 取最后一行非空内容(过滤 uv warning 行 / 错误堆栈)
  current=$(echo "$current_raw" | tail -1)
  if echo "$current_raw" | grep -qiE "Connection|OSError|cannot|refused|denied"; then
    warn "alembic 连不上 DB(可能尚未起 PG)— 真 staging 须确认 head"
  elif [[ -z "$current" ]]; then
    warn "无法读取 alembic current"
  elif [[ "$current" == *"$head_raw"* ]] || [[ "$current_raw" == *"$head_raw"* ]]; then
    ok "DB schema 是最新 head: $head_raw"
  else
    err "DB schema 不是 head;current=$current head=$head_raw"
  fi
else
  warn "uv 不在 PATH,跳过 alembic 检查"
fi

# ── 4. 黑名单代码模式(铁律 §3)──
echo ""
echo "[4/8] 代码模式黑名单"
if [[ -x "${ROOT}/scripts/check-blacklist.sh" ]]; then
  if bash "${ROOT}/scripts/check-blacklist.sh" >/dev/null 2>&1; then
    ok "无命中黑名单"
  else
    err "命中黑名单 — 跑 ./scripts/check-blacklist.sh 查"
  fi
else
  warn "check-blacklist.sh 不可执行"
fi

# ── 5. 单测 ──
echo ""
echo "[5/8] 单元测试"
if command -v uv >/dev/null 2>&1; then
  pushd "${ROOT}/backend" >/dev/null
  if uv run pytest tests/unit -q --tb=no >/tmp/preflight_test.log 2>&1; then
    pass=$(grep -oE '[0-9]+ passed' /tmp/preflight_test.log | head -1)
    ok "单测全绿(${pass})"
  else
    failed=$(grep -oE '[0-9]+ failed' /tmp/preflight_test.log | head -1)
    err "单测有失败(${failed:-未知})— 查 /tmp/preflight_test.log"
  fi
  popd >/dev/null
fi

# ── 6. 配额 / HITL gate / 飞轮信号配置 ──
echo ""
echo "[6/8] 关键配置"
if [[ -f "${ROOT}/backend/skills/playbooks/short_video.yaml" ]] \
   && grep -q "hitl_gate" "${ROOT}/backend/skills/playbooks/short_video.yaml"; then
  ok "短视频 Skill 含 HITL gate"
else
  err "短视频 Skill 没找到 HITL gate(铁律 14)"
fi
if [[ -f "${ROOT}/backend/skills/playbooks/ecommerce_detail_image.yaml" ]]; then
  ok "电商详情图 Skill 存在"
else
  err "电商详情图 Skill 缺失"
fi

# ── 7. K8s manifest 完整性 ──
echo ""
echo "[7/8] K8s manifests"
required_manifests=(
  "backend/deployment.yaml"
  "agents/text-deployment.yaml"
  "agents/document-deployment.yaml"
  "agents/image-deployment.yaml"
  "agents/av-deployment.yaml"
  "litellm/deployment.yaml"
  "datastore/qdrant.yaml"
  "frontend/deployment.yaml"
  "ingress.yaml"
  "kustomization.yaml"
  "heartbeat-consumer.yaml"
)
K8S="${ROOT}/../deploy/production/k8s"
for m in "${required_manifests[@]}"; do
  if [[ -f "${K8S}/${m}" ]]; then
    ok "k8s/${m}"
  else
    err "缺 k8s/${m}"
  fi
done

# ── 8. 监控 ──
echo ""
echo "[8/8] 可观测性"
[[ -f "${ROOT}/infrastructure/grafana/haole-dashboard.json" ]] && ok "Grafana dashboard JSON 存在" || warn "Grafana dashboard 未生成"
[[ -f "${ROOT}/infrastructure/prometheus/rules.yaml" ]] && ok "Prometheus rules 存在" || warn "Prometheus rules 未生成"

echo ""
echo "═══════════════════════════════════════════"
if [[ "$ERR_COUNT" -gt 0 ]]; then
  echo -e "${RED}阻塞 ${ERR_COUNT} 项 / 警告 ${WARN_COUNT} 项 — 不允许上线${NC}"
  exit 1
elif [[ "$WARN_COUNT" -gt 0 ]]; then
  echo -e "${YELLOW}阻塞 0 / 警告 ${WARN_COUNT} — 可上线但请知悉风险${NC}"
  exit 2
else
  echo -e "${GREEN}全绿 — 可上线${NC}"
  exit 0
fi
