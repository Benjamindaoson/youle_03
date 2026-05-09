"""Agent 工作状态计算(v4 §11 拟人化)。

状态枚举:
- working   正在执行任务
- idle      空闲(< 30min)
- fishing   摸鱼中(空闲 >30min,v4 #112)
- training  进修中(用户喂语料,V2)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_status import AgentStatus
from app.schemas.ws import WSEventType
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

Status = Literal["working", "idle", "fishing", "training"]
FISHING_THRESHOLD = timedelta(minutes=30)

VALID_AGENTS = ("agent_1", "agent_2", "agent_3", "agent_4", "ceo_assistant", "hr", "finance_manager")


def derive_status(*, current: Status, last_active_at: datetime) -> Status:
    """从原始状态 + 最近活跃时间推导派生状态。"""
    if current == "working" or current == "training":
        return current
    now = datetime.now(UTC)
    if now - last_active_at >= FISHING_THRESHOLD:
        return "fishing"
    return "idle"


async def set_status(
    session: AsyncSession,
    *,
    user_id: UUID,
    agent_id: str,
    status: Status,
    publish: bool = True,
    conversation_id: UUID | None = None,
) -> Status | None:
    """写库 + 推 WS。返回 publish 后的状态;不合法 agent_id 返回 None。

    conversation_id:WS 事件 payload 带上,前端 patchMemberStatus(convId, ...)
                    才能定位是哪个群的成员状态变化。LangGraph runner 派 step
                    时会传当前 task 的 conv.id;heartbeat consumer 没有特定群,
                    传 None(前端会按 user 全广播兜底)。
    """
    if agent_id not in VALID_AGENTS:
        return None
    now = datetime.now(UTC)
    # 读旧状态以避免无变化的噪声推送
    prev = await session.get(AgentStatus, (user_id, agent_id))
    prev_status = prev.status if prev else None

    stmt = (
        pg_insert(AgentStatus)
        .values(
            user_id=user_id,
            agent_id=agent_id,
            status=status,
            last_active_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "agent_id"],
            set_={"status": status, "last_active_at": now},
        )
    )
    await session.execute(stmt)
    await session.commit()

    if publish and prev_status != status:
        try:
            payload: dict[str, str | None] = {
                "type": WSEventType.AGENT_STATUS_CHANGED,
                "agent_id": agent_id,
                "status": status,
                "last_active_at": now.isoformat(),
                "conversation_id": str(conversation_id) if conversation_id else None,
            }
            await ws_manager.publish(str(user_id), payload)
        except Exception as e:
            log.warning("agent_status.publish_failed", err=str(e))
    return status


async def list_status(
    session: AsyncSession, *, user_id: UUID
) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(AgentStatus).where(AgentStatus.user_id == user_id)
        )
    ).scalars().all()
    by_agent: dict[str, AgentStatus] = {r.agent_id: r for r in rows}
    out: list[dict[str, str]] = []
    for aid in VALID_AGENTS:
        row = by_agent.get(aid)
        if row is None:
            out.append({"agent_id": aid, "status": "idle"})
            continue
        derived = derive_status(
            current=row.status,  # type: ignore[arg-type]
            last_active_at=row.last_active_at,
        )
        out.append({"agent_id": aid, "status": derived})
    return out
