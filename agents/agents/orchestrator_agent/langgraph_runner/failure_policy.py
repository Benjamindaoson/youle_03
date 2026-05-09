"""Skill failure_handling → 可执行重试参数(与 compiler 节点内循环对齐)。"""
from __future__ import annotations

import os
from typing import Any


def retry_config_for_step(step_id: str, failure_handling: dict[str, Any] | None) -> tuple[int, float]:
    """返回 (max_attempts, backoff_base_seconds)。

    - `on_failure: retry` / `retry_with_different_anchor` → 多读 ORCH_FAILURE_RETRY_MAX
    - 其它或未配置 → 1 次尝试(保持与历史行为一致)
    """
    fh = failure_handling or {}
    pol = fh.get(step_id) if isinstance(fh, dict) else None
    if not isinstance(pol, dict):
        return 1, 0.0
    action = str(pol.get("on_failure") or "")
    if action in {"retry_with_different_anchor", "retry"}:
        n = int(os.getenv("ORCH_FAILURE_RETRY_MAX", "3"))
        base = float(os.getenv("ORCH_FAILURE_RETRY_BACKOFF_BASE", "1.25"))
        return max(1, n), max(0.0, base)
    return 1, 0.0
