"""Agent 通信契约(与 backend.app.schemas.agent 对齐)。"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

AgentId = Literal["agent_1", "agent_2", "agent_3", "agent_4"]
AgentStatus = Literal["pending", "running", "completed", "failed", "pending_external"]

QUEUE_MAP: dict[AgentId, str] = {
    "agent_1": "agent_tasks:text",
    "agent_2": "agent_tasks:document",
    "agent_3": "agent_tasks:image",
    "agent_4": "agent_tasks:av",
}


class ArtifactRef(BaseModel):
    artifact_id: UUID
    type: str
    reference: str
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    task_id: UUID
    step_id: str
    agent_id: AgentId
    task_type: str
    user_id: UUID
    conversation_id: UUID
    inputs: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    routing_hints: dict[str, Any] = Field(default_factory=dict)
    skill_id: str | None = None
    skill_version: str | None = None
    timeout_seconds: int = 60
    #: 与 Skill YAML workflow 对齐;主编排派发时注入
    mcp_tools: list[str] = Field(default_factory=list)
    #: 主编排注入 — 与 backend.app.schemas.agent 对齐
    orchestration_run_id: UUID | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None
    dispatch_attempt: int = 0


class AgentResult(BaseModel):
    task_id: UUID
    step_id: str
    status: AgentStatus
    output: ArtifactRef | None = None
    extra_artifacts: list[ArtifactRef] = Field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    model_used: str | None = None
    error_detail: dict[str, Any] | None = None
    external_workflow_id: str | None = None


class StepOutput(BaseModel):
    """Typed output stored in LangGraph state's _upstream dict.

    Replaces the untyped dict[str, str] pattern — provides IDE completion
    and makes downstream step input resolution explicit.
    """

    step_id: str
    artifact_id: UUID = Field(default_factory=uuid4)
    type: str
    reference: str
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    status: AgentStatus = "completed"
    model_used: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None

    @classmethod
    def from_result(cls, result: AgentResult) -> "StepOutput":
        """Build StepOutput from a completed AgentResult."""
        if result.output is None:
            raise ValueError(f"AgentResult for step {result.step_id!r} has no output")
        return cls(
            step_id=result.step_id,
            artifact_id=result.output.artifact_id,
            type=result.output.type,
            reference=result.output.reference,
            extra_metadata=result.output.extra_metadata,
            status=result.status,
            model_used=result.model_used,
            cost_usd=result.cost_usd,
            duration_ms=result.duration_ms,
        )

    def to_artifact_ref(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=self.artifact_id,
            type=self.type,
            reference=self.reference,
            extra_metadata=self.extra_metadata,
        )
