from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import events as events_api
from app.schemas.events import EventType, UserEvent


class _DisconnectedRequest:
    async def is_disconnected(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_first_connection_replays_durable_conversation_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    event = UserEvent(
        type=EventType.TASK_STARTED,
        user_id=user_id,
        conversation_id=conversation_id,
        task_id=uuid4(),
        payload={"status": "running"},
    )
    repository = SimpleNamespace(replay=AsyncMock(return_value=[SimpleNamespace(to_schema=lambda: event)]))
    monkeypatch.setattr(events_api, "UserEventRepository", lambda _session: repository)
    monkeypatch.setattr(events_api.event_bus, "subscribe", AsyncMock(return_value=__import__("asyncio").Queue()))
    monkeypatch.setattr(events_api.event_bus, "unsubscribe", AsyncMock())
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(user_id=user_id))
    )

    response = await events_api.conversation_events(
        conversation_id=conversation_id,
        request=_DisconnectedRequest(),  # type: ignore[arg-type]
        last_event_id=None,
        user_id=user_id,
        session=session,  # type: ignore[arg-type]
    )
    frame = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    repository.replay.assert_awaited_once_with(
        user_id=user_id,
        conversation_id=conversation_id,
        after_event_id=None,
    )
    assert str(event.id).encode() in frame
    assert b"task_started" in frame
