"""记忆 Context Pack HTTP 出口 — 装配总裁助理/调试。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.services.memory import build_memory_context_pack
from app.services.memory.schemas import MemoryContextPack

router = APIRouter()


@router.get(
    "/{conversation_id}/memory/context-pack",
    response_model=MemoryContextPack,
    summary="装配本会话记忆包(Brief+滚动+任务卡+可选产物召回)",
)
async def get_memory_context_pack(
    conversation_id: UUID,
    recall_query: str | None = Query(default=None, max_length=500),
    task_limit: int = Query(default=5, ge=1, le=20),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MemoryContextPack:
    try:
        return await build_memory_context_pack(
            session,
            conversation_id=conversation_id,
            user_id=user_id,
            recall_query=recall_query,
            task_limit=task_limit,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
