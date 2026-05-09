"""子模块 8:HITL 网关管理器(ADR-010)。

任务编排器在 step 配置 hitl_gate 时,自动调本模块 open_gate。
LangGraph 暂停,等待用户响应:approve / modify / rollback(V2)。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hitl_gate import HITLGate
from app.schemas.ws import WSEventType
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

GateType = Literal["version_select", "quality_review", "final_approval"]


async def open_gate(
    *,
    session: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    step_id: str,
    gate_type: GateType,
    preview_artifact_id: UUID | None = None,
    timeout_seconds: int = 600,
) -> HITLGate:
    gate = HITLGate(
        id=uuid4(),
        task_id=task_id,
        step_id=step_id,
        gate_type=gate_type,
        preview_artifact_id=preview_artifact_id,
        timeout_seconds=timeout_seconds,
    )
    session.add(gate)
    await session.commit()
    await session.refresh(gate)

    await ws_manager.publish(
        str(user_id),
        {
            "type": WSEventType.HITL_GATE_OPENED,
            "task_id": str(task_id),
            "gate": {
                "id": str(gate.id),
                "step_id": step_id,
                "gate_type": gate_type,
                "timeout_seconds": timeout_seconds,
            },
            "preview_artifact": {"artifact_id": str(preview_artifact_id) if preview_artifact_id else None},
        },
    )
    log.info("hitl.gate_opened", task_id=str(task_id), gate=gate_type)
    return gate


async def close_gate(
    *,
    session: AsyncSession,
    gate_id: UUID,
    resolution: Literal["approved", "modified", "rolled_back", "timeout"],
    user_choice: dict[str, Any] | None = None,
) -> None:
    gate = await session.get(HITLGate, gate_id)
    if gate is None:
        return
    gate.resolution = resolution
    gate.user_choice = user_choice
    await session.commit()
    log.info("hitl.gate_closed", gate_id=str(gate_id), resolution=resolution)
