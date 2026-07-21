from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_user_id
from app.api.events import _stream_user_events
from app.db import get_session
from app.main import app
from app.models.conversation import Conversation
from app.schemas.events import EventType, UserEvent
from app.services.event_bus import EventBus


class _DisconnectAfter:
    def __init__(self, calls: int) -> None:
        self._remaining = calls

    async def is_disconnected(self) -> bool:
        self._remaining -= 1
        return self._remaining < 0


class _ConversationSession:
    def __init__(self, conversation: Conversation | None) -> None:
        self.conversation = conversation

    async def get(self, _model: Any, _key: Any) -> Conversation | None:
        return self.conversation


def _event(*, created_at: datetime | None = None) -> UserEvent:
    return UserEvent(
        type=EventType.MESSAGE_ADDED,
        user_id=uuid4(),
        conversation_id=uuid4(),
        payload={"content": "hello"},
        created_at=created_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_sse_route_requires_bearer_authentication() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/conversations/{uuid4()}/events")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_route_rejects_foreign_conversation() -> None:
    user_id = uuid4()
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        name="foreign",
        mode="group",
    )

    async def current_user() -> Any:
        return user_id

    async def session_override() -> Any:
        yield _ConversationSession(conversation)

    app.dependency_overrides[get_current_user_id] = current_user
    app.dependency_overrides[get_session] = session_override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/conversations/{conversation.id}/events"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sse_replays_events_in_order_with_stable_ids() -> None:
    bus = EventBus()
    user_id = str(uuid4())
    queue = await bus.subscribe(user_id)
    now = datetime.now(UTC)
    replay = [_event(created_at=now), _event(created_at=now + timedelta(seconds=1))]
    stream = _stream_user_events(
        request=_DisconnectAfter(10),
        user_id=user_id,
        queue=queue,
        replay=replay,
        bus=bus,
        heartbeat_seconds=30,
    )

    first = (await anext(stream)).decode()
    second = (await anext(stream)).decode()
    await stream.aclose()

    assert f"id: {replay[0].id}" in first
    assert f"id: {replay[1].id}" in second
    assert first.index(str(replay[0].id)) >= 0
    assert second.index(str(replay[1].id)) >= 0


@pytest.mark.asyncio
async def test_sse_emits_heartbeat_while_idle() -> None:
    bus = EventBus()
    user_id = str(uuid4())
    queue = await bus.subscribe(user_id)
    stream = _stream_user_events(
        request=_DisconnectAfter(10),
        user_id=user_id,
        queue=queue,
        replay=[],
        bus=bus,
        heartbeat_seconds=0.001,
    )

    frame = await asyncio.wait_for(anext(stream), 0.5)
    await stream.aclose()

    assert frame == b": heartbeat\n\n"


@pytest.mark.asyncio
async def test_sse_delivers_live_event_and_unsubscribes_on_close() -> None:
    bus = EventBus()
    user_id = str(uuid4())
    queue = await bus.subscribe(user_id)
    stream = _stream_user_events(
        request=_DisconnectAfter(10),
        user_id=user_id,
        queue=queue,
        replay=[],
        bus=bus,
        heartbeat_seconds=30,
    )
    next_frame = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    event = _event()

    await bus.publish_to_user(user_id, event.model_dump(mode="json"))
    frame = (await asyncio.wait_for(next_frame, 0.5)).decode()
    await stream.aclose()

    assert f"id: {event.id}" in frame
    assert "event: message_added" in frame
    assert bus.subscriber_count(user_id) == 0
