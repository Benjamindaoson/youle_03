"""Pytest 配置 — agents 包的本地测试根。

与 backend/tests/conftest.py 同思路:
- 让 tests 能 import `agents.*` 与 `app.*`(compiler.py 里有 `from app.schemas.agent import AgentTask`)
- 默认走 LITELLM_MOCK,避免外部网络
- 默认关闭 critic loop / dynamic plan 等新增 flag(测试要显式开启)

注:本文件**只**修改 sys.path / env vars,不 import 或修改 backend / frontend 代码。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# agents 包目录(F:\haole_mas-dev\agents),其 src 布局是 agents/agents/...
AGENTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENTS_ROOT.parent
BACKEND_ROOT = REPO_ROOT / "backend"

for p in (AGENTS_ROOT, BACKEND_ROOT):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 测试默认走 mock,不连真 LiteLLM
os.environ.setdefault("LITELLM_MOCK", "true")

# 默认关闭新增 flag — 单测要显式 monkeypatch 打开
os.environ.setdefault("ENABLE_DYNAMIC_PLAN", "false")
os.environ.setdefault("ENABLE_CRITIC_LOOP", "false")
os.environ.setdefault("ENABLE_EPISODE_RETRIEVAL", "false")
# OSS hydrate 默认关 — 单测里不连 MinIO
os.environ.setdefault("ORCH_HYDRATE_ENABLED", "false")
