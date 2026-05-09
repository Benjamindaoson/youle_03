"""任务 API。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.task import Task
from app.schemas.agent import AgentResult, AgentStatus, ArtifactRef
from app.services.agent_result_stream import publish_agent_result_to_stream
from agents.orchestrator_agent.interrupt import (
    V1_CLASSES,
    InterruptClassification,
    handle_interrupt,
)

log = structlog.get_logger(__name__)

router = APIRouter()


class TaskOut(BaseModel):
    """兼容旧响应形状;详情用 `TaskDetailOut`。"""

    id: UUID
    status: str
    skill_id: UUID | None
    progress: dict[str, Any]

    class Config:
        from_attributes = True


class TaskDetailOut(TaskOut):
    orchestration_run_id: str | None = None
    trace_id: str | None = None
    memory_card: dict[str, Any] | None = None
    failure_digest: str | None = None


def _failure_digest(error_detail: dict[str, Any] | None) -> str | None:
    if not error_detail:
        return None
    fr = error_detail.get("failure_reason")
    if isinstance(fr, str) and fr.strip():
        return fr.strip()[:500]
    err = error_detail.get("error") or error_detail.get("message")
    if isinstance(err, str) and err.strip():
        return err.strip()[:500]
    return None


class AnswerClarificationRequest(BaseModel):
    clarification_id: str
    field: str
    value: object


class InterruptRequest(BaseModel):
    interrupt_class: str  # A/B/C/D/E/F/G/H/I
    payload: dict[str, object] | None = None


@router.get("/{task_id}", response_model=TaskDetailOut)
async def get_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> TaskDetailOut:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if not (task.orchestration_run_id and task.trace_id):
        try:
            from agents.orchestrator_agent.runner_factory import make_runner

            runner = make_runner(session)
            snap = await runner.get_state(task_id)
            values = snap.get("values") or {}
            changed = False
            rid = values.get("orchestration_run_id")
            if rid and not task.orchestration_run_id:
                task.orchestration_run_id = str(rid).strip()[:36]
                changed = True
            tid = values.get("trace_id")
            if tid and not task.trace_id:
                task.trace_id = str(tid).strip()[:64]
                changed = True
            if changed:
                await session.commit()
        except Exception as e:
            log.warning("tasks.hydrate_observability_failed", task_id=str(task_id), err=str(e))
    return TaskDetailOut(
        id=task.id,
        status=task.status,
        skill_id=task.skill_id,
        progress=task.progress or {},
        orchestration_run_id=task.orchestration_run_id,
        trace_id=task.trace_id,
        memory_card=task.memory_card,
        failure_digest=_failure_digest(task.error_detail),
    )


class ExternalStepResultBody(BaseModel):
    step_id: str
    status: AgentStatus
    output: ArtifactRef | None = None
    extra_artifacts: list[ArtifactRef] = Field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    model_used: str | None = None
    error_detail: dict[str, Any] | None = None
    external_workflow_id: str | None = None


class ExternalStepPublished(BaseModel):
    status: str


class ClarificationAnswered(BaseModel):
    status: str


class InterruptTaskResponse(BaseModel):
    status: str
    interrupt_class: str
    action: str


class RollbackTaskResponse(BaseModel):
    status: str
    task_id: str
    target_step_id: str
    cleared_steps: list[str]
    rollback_count: int | None = None


@router.post("/{task_id}/external-step-result", response_model=ExternalStepPublished)
async def post_external_step_result(
    task_id: UUID,
    body: ExternalStepResultBody,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> ExternalStepPublished:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    result = AgentResult(
        task_id=task_id,
        step_id=body.step_id,
        status=body.status,
        output=body.output,
        extra_artifacts=body.extra_artifacts,
        cost_usd=body.cost_usd,
        duration_ms=body.duration_ms,
        model_used=body.model_used,
        error_detail=body.error_detail,
        external_workflow_id=body.external_workflow_id,
    )
    await publish_agent_result_to_stream(result)
    return ExternalStepPublished(status="published")


@router.post("/{task_id}/answer-clarification", response_model=ClarificationAnswered)
async def answer_clarification(
    task_id: UUID,
    body: AnswerClarificationRequest,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> ClarificationAnswered:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    fields = dict(task.collected_fields or {})
    fields[body.field] = body.value
    task.collected_fields = fields
    await session.commit()

    # 飞轮信号 2:聚合用户偏好(连续 3 次同选自动套用)
    from app.services.flywheel import flywheel

    await flywheel.emit_preference_update(
        session, user_id=task.user_id, fields={body.field: body.value}
    )
    return ClarificationAnswered(status="accepted")


class ConflictResolutionRequest(BaseModel):
    action: str  # queue / cancel_current / new_group


class ConflictResolveResponse(BaseModel):
    status: str
    next: str | None = None


@router.post("/{task_id}/resolve-conflict", response_model=ConflictResolveResponse)
async def resolve_conflict(
    task_id: UUID,
    body: ConflictResolutionRequest,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> ConflictResolveResponse:
    """一群一任务冲突解决(v4 #231)。"""
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if body.action == "cancel_current":
        from datetime import UTC, datetime

        from app.services.agent_cancel import publish_agent_task_cancel

        task.status = "cancelled"
        task.cancelled_at = datetime.now(UTC)
        await session.commit()
        await publish_agent_task_cancel(task.id)
        return ConflictResolveResponse(status="cancelled", next="send_message_again")
    if body.action == "queue":
        # 简化:仅标记 hint;真排队由 runner 在当前完成后扫描 conversation 内 pending
        return ConflictResolveResponse(status="queued")
    if body.action == "new_group":
        return ConflictResolveResponse(status="client_navigate", next="create_new_group")
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知操作:{body.action}")


@router.post("/{task_id}/interrupt", response_model=InterruptTaskResponse)
async def interrupt_task(
    task_id: UUID,
    body: InterruptRequest,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> InterruptTaskResponse:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if body.interrupt_class not in V1_CLASSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"V1 不支持中断 {body.interrupt_class}(C/D 推迟 V2)",
        )
    classification = InterruptClassification(
        interrupt_class=body.interrupt_class,  # type: ignore[arg-type]
        reason=(body.payload or {}).get("reason", ""),
    )
    action = await handle_interrupt(
        classification, task_state={"task_id": str(task_id), **(body.payload or {})}
    )
    return InterruptTaskResponse(
        status="received",
        interrupt_class=body.interrupt_class,
        action=action,
    )


# ─────────────────────────────────────────────────────────────────
# 时间旅行回滚
# 这是中断 C / D(回滚到第 N 步 / 改方向)的实现入口。
# ─────────────────────────────────────────────────────────────────
class RollbackRequest(BaseModel):
    target_step_id: str
    instruction: str | None = None  # 用户给"重做时该改什么"的指示


@router.post("/{task_id}/rollback", response_model=RollbackTaskResponse)
async def rollback_task(
    task_id: UUID,
    body: RollbackRequest,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> RollbackTaskResponse:
    """中断 C(回滚到第 N 步重做) / 中断 D(改方向) 的入口。

    依赖 LangGraph time-travel(graph.aget_state_history + aupdate_state)。
    """
    from agents.orchestrator_agent.runner_factory import make_runner

    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    runner = make_runner(session)
    out = await runner.rollback_to_step(
        task_id, target_step_id=body.target_step_id, instruction=body.instruction
    )
    return RollbackTaskResponse(
        status="rolled_back",
        task_id=str(task_id),
        target_step_id=body.target_step_id,
        cleared_steps=out.get("cleared_steps") or [],
        rollback_count=(out.get("state") or {}).get("rollback_count"),
    )


@router.get("/{task_id}/history")
async def task_history(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """LangGraph checkpoint 历史(时间线 UI 用)。"""
    from agents.orchestrator_agent.runner_factory import make_runner

    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    runner = make_runner(session)
    out: list[dict[str, Any]] = []
    async for snap in runner.get_history(task_id):
        out.append(snap)
    return out
