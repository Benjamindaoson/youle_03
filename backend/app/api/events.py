"""Authenticated conversation event stream with durable replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.config import settings
from app.db import get_session
from app.models.conversation import Conversation
from app.repositories.user_events import UserEventRepository
from app.schemas.events import UserEvent
from app.services.event_bus import EventBus, event_bus

router = APIRouter()


def _sse_frame(event: UserEvent) -> bytes:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return (
        f"id: {event.id}\nevent: {event.type.value}\ndata: {data}\n\n"
    ).encode()


async def _stream_user_events(
    *,
    request: Request | Any,
    user_id: str,
    queue: asyncio.Queue[dict[str, Any]],
    replay: list[UserEvent],
    bus: EventBus,
    heartbeat_seconds: float,
) -> AsyncIterator[bytes]:
    seen_ids: set[UUID] = set()
    try:
        for event in replay:
            seen_ids.add(event.id)
            yield _sse_frame(event)

        while not await request.is_disconnected():
            try:
                raw = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_seconds
                )
            except TimeoutError:
                yield b": heartbeat\n\n"
                continue

            event = UserEvent.model_validate(raw)
            if event.id in seen_ids:
                continue
            seen_ids.add(event.id)
            yield _sse_frame(event)
    finally:
        await bus.unsubscribe(user_id, queue)


@router.get("/{conversation_id}/events")
async def conversation_events(
    conversation_id: UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conversation.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该会话")

    after_event_id: UUID | None = None
    if last_event_id:
        try:
            after_event_id = UUID(last_event_id.strip())
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Last-Event-ID 无效"
            ) from exc

    queue = await event_bus.subscribe(str(user_id))
    try:
        replay_rows = (
            await UserEventRepository(session).replay(
                user_id=user_id,
                conversation_id=conversation_id,
                after_event_id=after_event_id,
            )
            if after_event_id is not None
            else []
        )
        replay = [row.to_schema() for row in replay_rows]
    except Exception:
        await event_bus.unsubscribe(str(user_id), queue)
        raise

    return StreamingResponse(
        _stream_user_events(
            request=request,
            user_id=str(user_id),
            queue=queue,
            replay=replay,
            bus=event_bus,
            heartbeat_seconds=settings.SSE_HEARTBEAT_SECONDS,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
