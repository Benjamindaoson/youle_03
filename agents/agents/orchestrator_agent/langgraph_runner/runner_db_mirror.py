"""LangGraph 编排状态镜射到 DB — 从 runner 拆分。"""

from __future__ import annotations

import contextlib
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.task import Task, TaskStep
from app.services.memory.hooks import enrich_artifact_inline


async def mirror_step_to_db(
    session: AsyncSession,
    *,
    task_id: UUID,
    step_id: str,
    step_result: dict[str, Any],
) -> UUID | None:
    """把 LangGraph state.step_results 的一条镜射回 task_steps 表 + artifacts 表。"""
    row = (
        await session.execute(
            select(TaskStep).where(
                TaskStep.task_id == task_id, TaskStep.step_id == step_id
            )
        )
    ).scalar_one_or_none()

    artifact_db_id: UUID | None = row.output_artifact_id if row else None
    artifact_ref = step_result.get("artifact_ref")
    if artifact_ref and artifact_db_id is None:
        task = await session.get(Task, task_id)
        if task is not None:
            artifact = Artifact(
                id=uuid4(),
                user_id=task.user_id,
                source_conversation_id=task.conversation_id,
                source_task_id=task.id,
                source_step_id=step_id,
                type=step_result.get("artifact_type") or "text",
                reference=artifact_ref,
                extra_metadata=step_result.get("artifact_metadata") or {},
                memory_tags=[],
            )
            enrich_artifact_inline(artifact)
            session.add(artifact)
            await session.flush()
            artifact_db_id = artifact.id

    if row is None:
        row = TaskStep(
            id=uuid4(),
            task_id=task_id,
            step_id=step_id,
            agent_id=step_result.get("agent_id"),
            task_type=step_result.get("task_type"),
            status=step_result.get("status") or "pending",
        )
        session.add(row)
    else:
        row.agent_id = step_result.get("agent_id") or row.agent_id
        row.task_type = step_result.get("task_type") or row.task_type
        row.status = step_result.get("status") or row.status
    if step_result.get("started_at"):
        with contextlib.suppress(Exception):
            row.started_at = datetime.fromisoformat(step_result["started_at"])
    if step_result.get("completed_at"):
        with contextlib.suppress(Exception):
            row.completed_at = datetime.fromisoformat(step_result["completed_at"])
    if step_result.get("duration_ms") is not None:
        row.duration_ms = int(step_result["duration_ms"])
    if step_result.get("cost_usd") is not None:
        row.cost_usd = Decimal(str(step_result["cost_usd"]))
    if step_result.get("model_used"):
        row.model_used = step_result["model_used"]
    if artifact_db_id is not None:
        row.output_artifact_id = artifact_db_id
    if step_result.get("error_detail"):
        row.error_detail = step_result["error_detail"]
    await session.commit()
    return artifact_db_id


async def mirror_state_steps_to_db(
    session: AsyncSession,
    *,
    task_id: UUID,
    state: dict[str, Any],
) -> None:
    """兜底同步 checkpoint 中的所有 step_results,覆盖 interrupt 事件未落库的节点。"""
    for step_id, step_result in (state.get("step_results") or {}).items():
        if isinstance(step_result, dict):
            await mirror_step_to_db(
                session,
                task_id=task_id,
                step_id=step_id,
                step_result=step_result,
            )
