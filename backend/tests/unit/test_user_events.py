from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models.user_event import UserEventRecord
from app.repositories.user_events import UserEventRepository
from app.schemas.events import EventType, UserEvent
from app.services.event_bus import EventBus
from app.services.event_publisher import EventPublisher


class _ScalarRows:
    def __init__(self, rows: list[UserEventRecord]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarRows:
        return self

    def all(self) -> list[UserEventRecord]:
        return self._rows


class _FakeSession:
    def __init__(
        self,
        *,
        cursor: UserEventRecord | None = None,
        rows: list[UserEventRecord] | None = None,
    ) -> None:
        self.cursor = cursor
        self.rows = rows or []
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.flushes = 0
        self.commits = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self, *_args: Any, **_kwargs: Any) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def scalar(self, statement: Any) -> UserEventRecord | None:
        self.statements.append(statement)
        return self.cursor

    async def execute(self, statement: Any) -> _ScalarRows:
        self.statements.append(statement)
        return _ScalarRows(self.rows)


def _record(
    *,
    event_id: UUID | None = None,
    user_id: UUID,
    conversation_id: UUID,
    created_at: datetime,
) -> UserEventRecord:
    return UserEventRecord(
        id=event_id or uuid4(),
        type=EventType.MESSAGE_ADDED,
        user_id=user_id,
        conversation_id=conversation_id,
        payload={"message_id": str(uuid4())},
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_append_preserves_preallocated_stable_event_id() -> None:
    session = _FakeSession()
    event = UserEvent(
        type=EventType.TASK_COMPLETED,
        user_id=uuid4(),
        conversation_id=uuid4(),
        task_id=uuid4(),
        payload={"status": "completed"},
    )

    row = await UserEventRepository(session).append(event)  # type: ignore[arg-type]

    assert row.id == event.id
    assert session.added == [row]
    assert session.flushes == 1
    assert event.model_dump(mode="json")["id"] == str(event.id)


@pytest.mark.asyncio
async def test_replay_is_scoped_and_ordered_after_last_event_id() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    now = datetime.now(UTC)
    cursor = _record(
        user_id=user_id,
        conversation_id=conversation_id,
        created_at=now,
    )
    later = [
        _record(
            user_id=user_id,
            conversation_id=conversation_id,
            created_at=now + timedelta(seconds=offset),
        )
        for offset in (1, 2)
    ]
    session = _FakeSession(cursor=cursor, rows=later)

    rows = await UserEventRepository(session).replay(  # type: ignore[arg-type]
        user_id=user_id,
        conversation_id=conversation_id,
        after_event_id=cursor.id,
    )

    assert rows == later
    assert len(session.statements) == 2
    sql = str(
        session.statements[-1].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert f"user_events.user_id = '{user_id}'" in sql
    assert f"user_events.conversation_id = '{conversation_id}'" in sql
    assert "user_events.created_at >" in sql
    assert "ORDER BY user_events.created_at ASC, user_events.id ASC" in sql


@pytest.mark.asyncio
async def test_unknown_or_foreign_cursor_replays_only_the_requested_stream() -> None:
    own_rows = [
        _record(
            user_id=uuid4(),
            conversation_id=uuid4(),
            created_at=datetime.now(UTC),
        )
    ]
    session = _FakeSession(cursor=None, rows=own_rows)

    rows = await UserEventRepository(session).replay(  # type: ignore[arg-type]
        user_id=uuid4(),
        conversation_id=uuid4(),
        after_event_id=uuid4(),
    )

    assert rows == own_rows
    assert len(session.statements) == 2
    sql = str(
        session.statements[-1].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "user_events.user_id =" in sql
    assert "user_events.conversation_id =" in sql


@pytest.mark.asyncio
async def test_publisher_uses_same_event_id_for_storage_and_live_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import event_bus as event_bus_module

    session = _FakeSession()
    bus = EventBus()
    user_id = uuid4()
    queue = await bus.subscribe(str(user_id))
    monkeypatch.setattr("app.services.event_publisher.SessionLocal", lambda: session)
    monkeypatch.setattr(event_bus_module, "event_bus", bus)

    event = await EventPublisher().publish_user_event(
        user_id=user_id,
        event_type=EventType.TASK_COMPLETED,
        conversation_id=uuid4(),
        payload={"status": "completed"},
    )
    live = await queue.get()
    stored = session.added[0]

    assert stored.id == event.id
    assert live["id"] == str(event.id)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_publisher_does_not_deliver_an_event_that_failed_to_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import event_bus as event_bus_module

    class FailingSession(_FakeSession):
        async def commit(self) -> None:
            raise RuntimeError("database unavailable")

    bus = EventBus()
    user_id = uuid4()
    queue = await bus.subscribe(str(user_id))
    monkeypatch.setattr(
        "app.services.event_publisher.SessionLocal", lambda: FailingSession()
    )
    monkeypatch.setattr(event_bus_module, "event_bus", bus)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await EventPublisher().publish_user_event(
            user_id=user_id,
            event_type=EventType.TASK_COMPLETED,
            conversation_id=uuid4(),
        )

    assert queue.empty()
