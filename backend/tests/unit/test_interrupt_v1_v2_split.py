"""V1 中断处理:C/D 返回 v2_deferred 动作 token(铁律 21),由 API 层转固定响应。"""

from __future__ import annotations

import pytest
from agents.orchestrator_agent.interrupt import (
    InterruptClassification,
    handle_interrupt,
)


@pytest.mark.parametrize("cls", ["C", "D"])
async def test_v2_classes_not_implemented(cls: str) -> None:
    classification = InterruptClassification(interrupt_class=cls)  # type: ignore[arg-type]
    action = await handle_interrupt(classification, task_state={})
    assert action == "v2_deferred"


@pytest.mark.parametrize("cls", ["A", "B", "E", "F", "G", "H", "I"])
async def test_v1_classes_handled(cls: str) -> None:
    classification = InterruptClassification(interrupt_class=cls)  # type: ignore[arg-type]
    # 不抛错即通过
    await handle_interrupt(classification, task_state={})
