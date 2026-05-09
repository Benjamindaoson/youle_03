"""Agent 之间通信契约。

Redis Streams 上传输的就是这两个 schema(铁律 13 兼容,通过队列不直连)。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AgentId = Literal["agent_1", "agent_2", "agent_3", "agent_4"]
AgentStatus = Literal["pending", "running", "completed", "failed", "pending_external"]


class ArtifactRef(BaseModel):
    artifact_id: UUID
    type: str
    reference: str  # oss://bucket/path
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """主编排 → Agent 的派活。"""

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
    #: Skill 步骤下发的 MCP 工具白名单,形如 mcp://<server>/<tool>
    mcp_tools: list[str] = Field(default_factory=list)
    #: 编排层稳定 run id(追踪 / 计费 / 幂等语义)
    orchestration_run_id: UUID | None = None
    #: hex trace id (建议 32 字符)
    trace_id: str | None = None
    #: 幂等键 — worker 可实现「同键同结果」
    idempotency_key: str | None = None
    #: 本 step 第几次 dispatch(从 0 起,含失败重试)
    dispatch_attempt: int = 0


class AgentResult(BaseModel):
    """Agent → 主编排 的回执。"""

    task_id: UUID
    step_id: str
    status: AgentStatus
    output: ArtifactRef | None = None
    extra_artifacts: list[ArtifactRef] = Field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    model_used: str | None = None
    error_detail: dict[str, Any] | None = None
    external_workflow_id: str | None = None  # 长任务(Celery)的句柄
