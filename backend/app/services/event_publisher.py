"""Transport-neutral publisher for durable user-facing events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from app.db import SessionLocal
from app.repositories.user_events import UserEventRepository
from app.schemas.events import EventType, UserEvent

log = structlog.get_logger(__name__)


def _optional_uuid(value: object) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


class EventPublisher:
    def __init__(self) -> None:
        self._persistence_enabled = True

    def start(self) -> None:
        self._persistence_enabled = True

    def stop(self) -> None:
        self._persistence_enabled = False

    async def publish_user_event(
        self,
        *,
        user_id: UUID,
        event_type: EventType | str,
        payload: dict[str, Any] | None = None,
        conversation_id: UUID | None = None,
        task_id: UUID | None = None,
        agent_id: str | None = None,
    ) -> UserEvent:
        event = UserEvent(
            type=EventType(str(event_type)),
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_id,
            agent_id=agent_id,
            payload=payload or {},
        )
        if self._persistence_enabled:
            await self._persist(event)

        from app.services import event_bus as event_bus_module

        await event_bus_module.event_bus.publish_to_user(
            str(user_id), event.model_dump(mode="json")
        )
        return event

    async def publish_legacy(
        self, user_id: str, payload: dict[str, Any]
    ) -> UserEvent:
        raw = dict(payload)
        event_type = raw.pop("type")
        return await self.publish_user_event(
            user_id=UUID(user_id),
            event_type=event_type,
            payload=raw,
            conversation_id=_optional_uuid(payload.get("conversation_id")),
            task_id=_optional_uuid(payload.get("task_id")),
            agent_id=(
                str(payload["agent_id"])
                if payload.get("agent_id") is not None
                else None
            ),
        )

    async def _persist(self, event: UserEvent) -> None:
        try:
            async with SessionLocal() as session:
                await UserEventRepository(session).append(event)
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - log context, then fail closed
            log.error(
                "user_event.persistence_failed",
                event_id=str(event.id),
                event_type=event.type.value,
                user_id=str(event.user_id),
                err=str(exc),
            )
            # Durable replay is part of the event contract. Publishing a live
            # event that was not stored would make reconnecting clients lose it.
            raise


event_publisher = EventPublisher()
