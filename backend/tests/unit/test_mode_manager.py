"""主编排子模块 7 — 模式管理器:配额规则。"""

from __future__ import annotations

import pytest
from agents.orchestrator_agent.mode_manager import consumes_task_quota


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("auto", True),
        ("plan", False),
        ("ask", False),
        (None, False),
    ],
)
def test_quota_rule(mode, expected) -> None:
    """铁律 20:Plan/Ask 不消耗任务配额,只算 token;Auto 才扣任务配额。"""
    assert consumes_task_quota(mode) is expected
