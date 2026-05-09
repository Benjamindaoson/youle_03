#!/usr/bin/env bash
# 代码模式黑名单(对齐 CLAUDE.md §3)。本地或 pre-commit 跑。
#
# 实现要点:
# - **import 级**模式必须出现在行首(非 docstring 中部);加 `^[[:space:]]*` 锚点
# - **except: pass** 真正的反模式必须**连续两行**(用 `-A 1` + awk 确认下一行只有 pass)
# - call_other_agent stub 在 `cross_call.py` 永远 raise NotImplementedError — 本身合法,只查调用点
set -euo pipefail
cd "$(dirname "$0")/.."

violations=0
warnings=0

real_code_grep() {
  local pattern="$1"
  grep -rn -E --include="*.py" "^[[:space:]]*${pattern}" \
       --exclude-dir=__pycache__ \
       backend/app agents agents/mcp_servers backend/flywheel 2>/dev/null || true
}

check_import() {
  local pattern="$1"
  local desc="$2"
  local hits
  hits=$(real_code_grep "$pattern")
  if [[ -n "$hits" ]]; then
    echo "$hits"
    echo "✗ violation: $desc"
    violations=$((violations + 1))
  fi
}

check_import 'import openai$' '禁止 import openai(铁律 7,走 app.router)'
check_import 'import anthropic$' '禁止 import anthropic'
check_import 'from openai import' '同上'
check_import 'from anthropic import' '同上'
check_import 'OpenAI\(' '禁止直接构造 OpenAI()'

# Agent 跨调:函数定义本身在 cross_call.py 是合法 stub(永远 raise NotImplementedError);只查调用点
hits=$(grep -rn -E --include="*.py" 'call_other_agent\(' \
       backend/app agents agents/mcp_servers backend/flywheel 2>/dev/null \
       | grep -v 'cross_call.py' \
       | grep -v -E ':[[:space:]]*#' \
       | grep -v -E ':[[:space:]]*"""' \
       | grep -v 'def call_other_agent' || true)
if [[ -n "$hits" ]]; then
  echo "$hits"
  echo "✗ violation: ADR-002:Agent 不能跨调用 call_other_agent"
  violations=$((violations + 1))
fi

# except (Exception)?: pass 真正的反模式 — 用 -A 1 看下一行
hits=$(grep -rn -E --include="*.py" -A 1 '^[[:space:]]*except( Exception)?:[[:space:]]*$' \
       backend/app agents agents/mcp_servers backend/flywheel 2>/dev/null \
       | awk '
         BEGIN { prev="" }
         /^--$/ { prev=""; next }
         {
           # grep -A 1 输出格式: "path.py-NNN-    pass"(分隔符是 -)
           if (prev != "" && $0 ~ /-[[:space:]]*pass[[:space:]]*$/) {
             print prev; print $0;
           }
           prev = $0
         }')
if [[ -n "$hits" ]]; then
  echo "$hits"
  echo "✗ violation: 禁止 except: pass 静默吞异常(铁律 12)"
  violations=$((violations + 1))
fi

# print 走 structlog(警告 — 不阻塞)
hits=$(grep -rn --include="*.py" -E '^[[:space:]]*print\(' \
       backend/app agents agents/mcp_servers backend/flywheel 2>/dev/null || true)
if [[ -n "$hits" ]]; then
  echo "$hits" | head -10
  echo "⚠ warning: 建议用 structlog 替换 print(铁律 12)"
  warnings=$((warnings + 1))
fi

echo ""
if [[ $violations -gt 0 ]]; then
  echo "❌ 存在 $violations 处违规 / $warnings 处警告 — 见 CLAUDE.md §3"
  exit 1
fi
if [[ $warnings -gt 0 ]]; then
  echo "⚠️  无违规,有 $warnings 处警告"
fi
echo "✅ 代码模式黑名单通过"
