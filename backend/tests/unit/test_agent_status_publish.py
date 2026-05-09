"""set_status:写库后通过 ws_manager.publish 推 AGENT_STATUS_CHANGED。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.agent_status import AgentStatus


def _stub_session(prev_status: str | None):
    """模拟 AsyncSession,带一个 get(AgentStatus, key) 的存根。"""
    session = MagicMock()
    if prev_status is None:
        session.get = AsyncMock(return_value=None)
    else:
        prev = MagicMock(spec=AgentStatus)
        prev.status = prev_status
        prev.last_active_at = datetime.now(UTC)
        session.get = AsyncMock(return_value=prev)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_set_status_publishes_when_changed(monkeypatch) -> None:
    publish = AsyncMock()
    monkeypatch.setattr("app.services.agent_status.ws_manager.publish", publish)

    session = _stub_session(prev_status="idle")
    from app.services.agent_status import set_status

    user_id = uuid4()
    out = await set_status(
        session,
        user_id=user_id,
        agent_id="agent_1",
        status="working",
    )
    assert out == "working"
    publish.assert_awaited_once()
    args, _ = publish.await_args
    assert args[0] == str(user_id)
    payload = args[1]
    assert payload["type"] == "agent_status_changed"
    assert payload["agent_id"] == "agent_1"
    assert payload["status"] == "working"


@pytest.mark.asyncio
async def test_set_status_does_not_publish_when_unchanged(monkeypatch) -> None:
    publish = AsyncMock()
    monkeypatch.setattr("app.services.agent_status.ws_manager.publish", publish)

    session = _stub_session(prev_status="working")
    from app.services.agent_status import set_status

    await set_status(
        session,
        user_id=uuid4(),
        agent_id="agent_1",
        status="working",  # 与旧值一致 — 不推送
    )
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_status_invalid_agent_id_returns_none(monkeypatch) -> None:
    publish = AsyncMock()
    monkeypatch.setattr("app.services.agent_status.ws_manager.publish", publish)

    session = _stub_session(prev_status=None)
    from app.services.agent_status import set_status

    out = await set_status(
        session,
        user_id=uuid4(),
        agent_id="not_a_real_agent",
        status="working",
    )
    assert out is None
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_status_payload_carries_conversation_id(monkeypatch) -> None:
    """新契约:WS payload 必带 conversation_id(可为 None),前端按群定位成员状态。"""
    publish = AsyncMock()
    monkeypatch.setattr("app.services.agent_status.ws_manager.publish", publish)

    session = _stub_session(prev_status="idle")
    from app.services.agent_status import set_status

    conv_id = uuid4()
    await set_status(
        session,
        user_id=uuid4(),
        agent_id="agent_3",
        status="working",
        conversation_id=conv_id,
    )
    payload = publish.await_args.args[1]
    assert payload["conversation_id"] == str(conv_id)


@pytest.mark.asyncio
async def test_set_status_payload_conversation_id_can_be_none(monkeypatch) -> None:
    """heartbeat consumer 不带 conversation_id 时,payload 字段为 None(前端兜底广播)。"""
    publish = AsyncMock()
    monkeypatch.setattr("app.services.agent_status.ws_manager.publish", publish)

    session = _stub_session(prev_status="idle")
    from app.services.agent_status import set_status

    await set_status(
        session,
        user_id=uuid4(),
        agent_id="agent_3",
        status="working",
        # 不传 conversation_id
    )
    payload = publish.await_args.args[1]
    assert "conversation_id" in payload
    assert payload["conversation_id"] is None
