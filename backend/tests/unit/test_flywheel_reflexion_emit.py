"""Reflexion 闭环:emit_trace 在 failure_reason 非空时自动 emit 'reflexion' 信号到 Stream。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_emit_trace_failure_emits_reflexion_signal(monkeypatch) -> None:
    """failure_reason 非空 → Stream 应当收到 type=reflexion 的事件。"""
    captured: list[tuple[str, dict]] = []

    async def _fake_emit(signal_type: str, payload: dict) -> None:
        captured.append((signal_type, payload))

    monkeypatch.setattr("app.services.flywheel._emit_stream", _fake_emit)

    # Mock SQLAlchemy session: add+commit 不实际执行
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    from app.services.flywheel import flywheel

    await flywheel.emit_trace(
        session,
        task_id=uuid4(),
        user_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        duration_ms=1234,
        cost_usd=Decimal("0.05"),
        failure_reason="step research timed out",
        full_trace={"steps": [{"step_id": "research", "status": "failed"}]},
    )

    # 应至少 2 次 emit:trace + reflexion
    types = [t for t, _ in captured]
    assert "trace" in types
    assert "reflexion" in types

    # reflexion payload 检查
    reflexion_payload = next(p for t, p in captured if t == "reflexion")
    assert reflexion_payload["failure_reason"] == "step research timed out"
    assert "research" in reflexion_payload["trace_excerpt"]


@pytest.mark.asyncio
async def test_emit_trace_high_satisfaction_emits_skill_drafter(monkeypatch) -> None:
    """user_satisfaction>=4 → Stream 应当收到 type=skill_drafter 的事件。"""
    captured: list[tuple[str, dict]] = []

    async def _fake_emit(signal_type: str, payload: dict) -> None:
        captured.append((signal_type, payload))

    monkeypatch.setattr("app.services.flywheel._emit_stream", _fake_emit)

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    from app.services.flywheel import flywheel

    await flywheel.emit_trace(
        session,
        task_id=uuid4(),
        user_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        duration_ms=1000,
        cost_usd=Decimal("0.01"),
        user_satisfaction=5,
    )

    types = [t for t, _ in captured]
    assert "skill_drafter" in types


@pytest.mark.asyncio
async def test_emit_trace_success_no_reflexion(monkeypatch) -> None:
    """success 路径(failure_reason 为 None)→ 不 emit reflexion。"""
    captured: list[tuple[str, dict]] = []

    async def _fake_emit(signal_type: str, payload: dict) -> None:
        captured.append((signal_type, payload))

    monkeypatch.setattr("app.services.flywheel._emit_stream", _fake_emit)

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    from app.services.flywheel import flywheel

    await flywheel.emit_trace(
        session,
        task_id=uuid4(),
        user_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        duration_ms=1000,
        cost_usd=Decimal("0.01"),
        # 没传 failure_reason / user_satisfaction
    )

    types = [t for t, _ in captured]
    assert "trace" in types
    assert "reflexion" not in types
    assert "skill_drafter" not in types
