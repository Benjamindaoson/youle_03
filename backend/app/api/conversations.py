"""会话 API(v3.0 ADR-014:三模式同群切换)。

注意:`derive-work-group` / `back-to-discuss` 已废弃,改用 `switch-work-mode`(铁律 17)。
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.conversation import Conversation
from app.models.mode_switch_log import ModeSwitchLog
from app.models.user import User
from app.schemas.ws import WSEventType
from app.services.quota_enforce import QuotaExceeded, enforce_group_creation
from app.ws.manager import ws_manager

router = APIRouter()


WorkMode = Literal["plan", "ask", "auto"]
ConversationMode = Literal["main_session", "group", "private_chat"]


class ConversationCreate(BaseModel):
    mode: ConversationMode = "group"
    work_mode: WorkMode | None = None
    skill_id: UUID | None = None
    name: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mode: ConversationMode
    work_mode: WorkMode | None
    status: str

class SwitchWorkModeRequest(BaseModel):
    target: WorkMode
    triggered_by: Literal["user", "orchestrator"] = "user"


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[Conversation]:
    rows = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.last_message_at.desc().nulls_last())
    )
    return list(rows.scalars().all())


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    # 工作群创建走配额闸门(v4 #345);main_session / private_chat 不计
    if body.mode == "group":
        try:
            await enforce_group_creation(session, user=user)
        except QuotaExceeded as e:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                detail={"code": e.code, "detail": e.detail},
            ) from e
    conv = Conversation(
        user_id=user_id,
        name=body.name or "新会话",
        mode=body.mode,
        work_mode=body.work_mode,
        skill_id=body.skill_id,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    await ws_manager.publish(
        str(user_id),
        {
            "type": WSEventType.CONVERSATION_CREATED,
            "conversation_id": str(conv.id),
            "mode": conv.mode,
        },
    )
    return conv


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return conv


VALID_PRIVATE_AGENTS = {
    "ceo_assistant",
    "agent_1",
    "agent_2",
    "agent_3",
    "agent_4",
    "hr",
    "finance_manager",
}


@router.post("/private-chat/{agent_id}", response_model=ConversationOut)
async def open_private_chat(
    agent_id: str,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    """获取或创建用户与某 Agent 的私聊会话(v4 §237-240)。

    幂等:同一用户 + 同一 agent_id 永远只有 1 个 active 私聊。
    """
    if agent_id not in VALID_PRIVATE_AGENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知 Agent:{agent_id}")
    existing = (
        await session.execute(
            select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.mode == "private_chat",
                Conversation.private_chat_agent_id == agent_id,
                Conversation.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    conv = Conversation(
        user_id=user_id,
        name=f"与 {agent_id} 的私聊",
        mode="private_chat",
        private_chat_agent_id=agent_id,
        status="active",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@router.get("/{conversation_id}/brief")
async def get_brief(
    conversation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return dict(conv.brief or {"完成度": 0.0, "字段": {}, "决策日志": []})


@router.post("/{conversation_id}/brief/reset")
async def reset_brief(
    conversation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    conv.brief = {"完成度": 0.0, "字段": {}, "决策日志": []}
    await session.commit()
    return dict(conv.brief)


@router.post("/{conversation_id}/switch-work-mode")
async def switch_work_mode(
    conversation_id: UUID,
    body: SwitchWorkModeRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """v3.0 ADR-014:同群切换 plan/ask/auto。"""
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.mode != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅群会话支持模式切换")

    from_mode = conv.work_mode
    conv.work_mode = body.target
    session.add(
        ModeSwitchLog(
            conversation_id=conv.id,
            from_mode=from_mode,
            to_mode=body.target,
            triggered_by=body.triggered_by,
        )
    )
    await session.commit()

    return {
        "conversation": ConversationOut.model_validate(conv).model_dump(),
        "ws_event": {
            "type": WSEventType.WORK_MODE_CHANGED,
            "conversation_id": str(conv.id),
            "from": from_mode,
            "to": body.target,
        },
    }


# ─────────────────────────────────────────────────────────────────
# 群成员列表(主会话 7 / 普通群 5 / 私聊 1 — 铁律 18 + ADR-013)
# ─────────────────────────────────────────────────────────────────
class AgentMember(BaseModel):
    id: str        # ceo_assistant / agent_1..4 / hr / finance_manager
    status: str    # working / idle / fishing / training


# 主会话:7 角色;普通群:5 角色(无 HR / 财务,铁律 18)
_MAIN_SESSION_ROLES = (
    "ceo_assistant",
    "agent_1",
    "agent_2",
    "agent_3",
    "agent_4",
    "hr",
    "finance_manager",
)
_GROUP_ROLES = ("ceo_assistant", "agent_1", "agent_2", "agent_3", "agent_4")


def _members_for_mode(mode: str, *, private_chat_agent_id: str | None = None) -> list[str]:
    if mode == "main_session":
        return list(_MAIN_SESSION_ROLES)
    if mode == "group":
        return list(_GROUP_ROLES)
    if mode == "private_chat":
        return [private_chat_agent_id or "ceo_assistant"]
    return []


@router.get("/{conversation_id}/members", response_model=list[AgentMember])
async def list_members(
    conversation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[AgentMember]:
    """会话成员 + 各自当前工作状态(派生自 agent_status 表)。"""
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if conv.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")

    role_ids = _members_for_mode(conv.mode, private_chat_agent_id=conv.private_chat_agent_id)
    if not role_ids:
        return []

    # 一次查 agent_status,合并状态
    from app.models.agent_status import AgentStatus

    rows = (
        await session.execute(
            select(AgentStatus).where(
                AgentStatus.user_id == user_id,
                AgentStatus.agent_id.in_(role_ids),
            )
        )
    ).scalars().all()
    status_map: dict[str, str] = {r.agent_id: r.status for r in rows}

    return [
        AgentMember(id=rid, status=status_map.get(rid, "idle"))
        for rid in role_ids
    ]
