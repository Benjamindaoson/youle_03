"""会话服务(创建 / 切换模式 / 发消息)。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


async def create_main_session(
    session: AsyncSession, *, user_id: UUID, name: str = "主会话"
) -> Conversation:
    conv = Conversation(
        id=uuid4(),
        user_id=user_id,
        name=name,
        mode="main_session",
        status="active",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def append_message(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    role: str,
    content: str | None,
    content_type: str = "text",
    extra_metadata: dict[str, Any] | None = None,
) -> Message:
    msg = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        content_type=content_type,
        extra_metadata=extra_metadata or {},
    )
    session.add(msg)
    conv = await session.get(Conversation, conversation_id)
    if conv is not None:
        conv.last_message_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(msg)
    return msg
