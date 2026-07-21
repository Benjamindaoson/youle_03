"""主编排消息入口 — 端到端胶水(铁律 1:单一调度者)。

POST /api/conversations/:id/messages
  → 校验会话与用户、配额闸门
  → 写 messages（及 Plan 模式下 Brief 防抖）
  → 后台触发滚动摘要
  → 决策管线见 ``app.services.send_message_handlers.dispatch_send_message``（单一事实来源）
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import SessionLocal, get_session
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.message import Message as MessageOut
from app.schemas.send_message import SendMessageRequest, SendMessageResponse
from app.services.brief_builder import brief_debouncer
from app.services.conversation import append_message
from app.services.quota_enforce import QuotaExceeded, enforce_plan_turn
from app.services.send_message_handlers import _parse_mentions, dispatch_send_message

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
async def list_messages(
    conversation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[Message]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conversation.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该会话")
    rows = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(rows.scalars().all())

# 兼容单测：`test_mention_routing` 从本模块导入
__all__ = [
    "router",
    "SendMessageRequest",
    "SendMessageResponse",
    "_parse_mentions",
    "list_messages",
    "send_message",
]


async def _maybe_refresh_memory_fire_and_forget(conversation_id: UUID) -> None:
    try:
        async with SessionLocal() as s:
            from app.services.memory import maybe_update_rolling_summary

            await maybe_update_rolling_summary(s, conversation_id=conversation_id)
    except Exception as e:
        log.warning("messages.memory_refresh_failed", err=str(e))


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> SendMessageResponse:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    user = await session.get(User, conv.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")

    try:
        await enforce_plan_turn(session, conversation=conv, user=user)
    except QuotaExceeded as e:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, e.detail) from e

    parsed_mentions = _parse_mentions(body.content, body.mentions or [])
    user_msg = await append_message(
        session,
        conversation_id=conv.id,
        role=body.role,
        content=body.content,
        extra_metadata={"mentions": parsed_mentions} if parsed_mentions else None,
    )

    if conv.work_mode == "plan":
        await brief_debouncer.push(
            conv.id, {"role": body.role, "content": body.content}
        )

    asyncio.create_task(_maybe_refresh_memory_fire_and_forget(conv.id))

    return await dispatch_send_message(
        session=session,
        conv=conv,
        user=user,
        body=body,
        user_msg=user_msg,
        parsed_mentions=parsed_mentions,
    )
