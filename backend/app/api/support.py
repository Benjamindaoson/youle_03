"""HR / 财务经理 API(铁律 18:仅主会话,API 直接响应)。

GET /api/quota/me                          → 当前配额画像
GET /api/quota/me/billing?month=2026-05    → 月度账单
POST /api/support/hr/respond               → HR 直接对话
POST /api/support/finance/respond          → 财务经理直接对话
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.conversation import Conversation
from app.models.quota import QuotaUsage
from app.models.user import User
from app.schemas.ws import WSEventType
from app.services.support_agent import (
    QUOTA_PLAN_LIMITS,
    finance_quota_summary,
    finance_respond,
    hr_respond,
    needs_quota_warning,
)
from app.ws.manager import ws_manager

router = APIRouter()
log = structlog.get_logger(__name__)


# ── 模型 ──
class SupportRequest(BaseModel):
    conversation_id: UUID
    content: str


class SupportResponse(BaseModel):
    message_id: UUID
    role: str
    content: str
    quota_warning: list[str] = []


# ── 配额查询 ──
@router.get("/agent-status/me")
async def my_agent_status(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, str]]:
    """所有 Agent 的派生状态(working/idle/fishing/training)— v4 #109-113。"""
    from app.services.agent_status import list_status

    return await list_status(session, user_id=user_id)


@router.get("/quota/me")
async def my_quota(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    summary = await finance_quota_summary(session, user_id=user_id, plan=user.plan)
    summary["limits_table"] = QUOTA_PLAN_LIMITS
    summary["warnings"] = needs_quota_warning(summary)
    return summary


@router.get("/quota/me/billing")
async def my_billing(
    month: str | None = None,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """月度账单:按 quota_type 聚合本月使用量。"""
    target_month = month or datetime.now(UTC).strftime("%Y-%m")
    rows = (
        await session.execute(
            select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.period.like(f"{target_month}%"),
            )
        )
    ).scalars().all()
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r.quota_type] = by_type.get(r.quota_type, 0) + r.consumed
    return {"month": target_month, "by_quota_type": by_type, "total_items": sum(by_type.values())}


# ── HR 直对话 ──
@router.post("/support/hr/respond", response_model=SupportResponse)
async def hr_dialogue(
    body: SupportRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> SupportResponse:
    conv = await session.get(Conversation, body.conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.mode != "main_session":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "HR 仅在主会话(铁律 18)"
        )
    msg = await hr_respond(
        session, conversation_id=conv.id, user_message=body.content
    )
    return SupportResponse(
        message_id=msg.id, role="hr", content=msg.content or ""
    )


# ── 财务经理直对话 ──
@router.post("/support/finance/respond", response_model=SupportResponse)
async def finance_dialogue(
    body: SupportRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> SupportResponse:
    conv = await session.get(Conversation, body.conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.mode != "main_session":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "财务经理仅在主会话(铁律 18)"
        )
    user = await session.get(User, user_id)
    plan = (user.plan if user else None) or "free"
    msg = await finance_respond(
        session,
        conversation_id=conv.id,
        user_id=user_id,
        user_message=body.content,
        plan=plan,
    )
    summary = await finance_quota_summary(session, user_id=user_id, plan=plan)
    warnings = needs_quota_warning(summary)
    if warnings:
        try:
            await ws_manager.publish(
                str(user_id),
                {
                    "type": WSEventType.QUOTA_WARNING,
                    "warnings": warnings,
                    "source": "finance_respond",
                },
            )
        except Exception as e:
            log.warning("support.quota_ws_publish_failed", err=str(e))
    return SupportResponse(
        message_id=msg.id,
        role="finance_manager",
        content=msg.content or "",
        quota_warning=warnings,
    )
