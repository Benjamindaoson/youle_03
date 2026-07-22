from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.event_bus import EventBus
from app.ws.manager import WSManager


@pytest.mark.asyncio
async def test_publish_delivers_to_every_local_subscriber() -> None:
    bus = EventBus(queue_maxsize=2)
    user_id = str(uuid4())
    first = await bus.subscribe(user_id)
    second = await bus.subscribe(user_id)

    await bus.publish_to_user(user_id, {"type": "message_added"})

    assert await asyncio.wait_for(first.get(), 0.5) == {"type": "message_added"}
    assert await asyncio.wait_for(second.get(), 0.5) == {"type": "message_added"}


@pytest.mark.asyncio
async def test_full_subscriber_queue_discards_oldest_event() -> None:
    bus = EventBus(queue_maxsize=2)
    queue = await bus.subscribe("user-1")
    queue.put_nowait({"sequence": 1})
    queue.put_nowait({"sequence": 2})

    await bus.publish_to_user("user-1", {"sequence": 3})

    assert queue.get_nowait() == {"sequence": 2}
    assert queue.get_nowait() == {"sequence": 3}


@pytest.mark.asyncio
async def test_unsubscribe_removes_local_queue() -> None:
    bus = EventBus()
    queue = await bus.subscribe("user-1")
    assert bus.subscriber_count("user-1") == 1

    await bus.unsubscribe("user-1", queue)

    assert bus.subscriber_count("user-1") == 0


class _RedisRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> None:
        if self.fail:
            raise ConnectionError("redis unavailable")
        self.messages.append((channel, payload))


@pytest.mark.asyncio
async def test_redis_payload_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RedisRecorder()

    async def fake_get_redis() -> _RedisRecorder:
        return recorder

    monkeypatch.setattr("app.redis_client.get_redis", fake_get_redis)
    bus = EventBus()
    bus._redis_available = True
    event_id = uuid4()

    await bus.publish_to_user(
        "user-1",
        {
            "type": "message_added",
            "id": event_id,
            "created_at": datetime(2026, 7, 21, tzinfo=UTC),
            "cost": Decimal("1.25"),
        },
    )

    channel, raw = recorder.messages[0]
    assert channel == "haole:events:user-1"
    assert json.loads(raw) == {
        "type": "message_added",
        "id": str(event_id),
        "created_at": "2026-07-21T00:00:00+00:00",
        "cost": "1.25",
    }


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_local_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_redis() -> _RedisRecorder:
        return _RedisRecorder(fail=True)

    monkeypatch.setattr("app.redis_client.get_redis", fake_get_redis)
    bus = EventBus()
    bus._redis_available = True
    queue = await bus.subscribe("user-1")

    await bus.publish_to_user("user-1", {"type": "task_failed"})

    assert await asyncio.wait_for(queue.get(), 0.5) == {"type": "task_failed"}


@pytest.mark.asyncio
async def test_ws_manager_publish_uses_shared_event_bus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import event_bus as event_bus_module
    from app.services.event_publisher import event_publisher

    bus = EventBus()
    monkeypatch.setattr(event_bus_module, "event_bus", bus)
    monkeypatch.setattr(event_publisher, "_persistence_enabled", False)
    user_id = str(uuid4())
    queue = await bus.subscribe(user_id)

    await WSManager().publish(user_id, {"type": "task_completed"})

    delivered = await asyncio.wait_for(queue.get(), 0.5)
    assert delivered["type"] == "task_completed"
    assert delivered["payload"] == {}
    assert delivered["id"]
