"""WebSocket 事件类型(对齐 docs/ARCHITECTURE.md §6.5)。

前端 lib/ws-events.ts 与本文件保持一致(手写 / 校验)。

**与实现的对齐说明（后端推送来源）**
- 已在 `ws_manager.publish` / `LangGraphTaskRunner.publish` / 相关 API 中发送：`conversation_status_changed`、`message_added`、`work_mode_changed`、`brief_updated`、`mode_choice_required`、`agent_status_changed`、`step_started`、`step_completed`、`task_completed`、`task_failed`、`hitl_gate_opened`（两种 payload 形态）、`clarification_required`（见 `messages`）、`conversation_created`（见 `create_conversation`）、`hitl_gate_closed`（见 `resolve_hitl`）、`quota_warning`（见财务支持对话）、`pong`（心跳）。
- **保留/预留**：`step_streaming` 主要为长文本等流式场景；当前主编排 HTTP 路径未统一推送该类型（若存在流式实现，由对应 agent 侧写 stream 或后续接入）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WSEventType(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_STATUS_CHANGED = "conversation_status_changed"
    MESSAGE_ADDED = "message_added"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_STREAMING = "step_streaming"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    CLARIFICATION_REQUIRED = "clarification_required"
    MODE_CHOICE_REQUIRED = "mode_choice_required"
    WORK_MODE_CHANGED = "work_mode_changed"
    BRIEF_UPDATED = "brief_updated"
    HITL_GATE_OPENED = "hitl_gate_opened"
    HITL_GATE_CLOSED = "hitl_gate_closed"
    QUOTA_WARNING = "quota_warning"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    PONG = "pong"


class WSEventBase(BaseModel):
    type: WSEventType


class StepStarted(WSEventBase):
    type: Literal[WSEventType.STEP_STARTED] = WSEventType.STEP_STARTED
    task_id: UUID
    step_id: str
    agent_id: str


class StepCompleted(WSEventBase):
    type: Literal[WSEventType.STEP_COMPLETED] = WSEventType.STEP_COMPLETED
    task_id: UUID
    step_id: str
    artifact: dict[str, Any]


class StepStreaming(WSEventBase):
    type: Literal[WSEventType.STEP_STREAMING] = WSEventType.STEP_STREAMING
    task_id: UUID
    step_id: str
    chunk: str


class WorkModeChanged(WSEventBase):
    type: Literal[WSEventType.WORK_MODE_CHANGED] = WSEventType.WORK_MODE_CHANGED
    conversation_id: UUID
    from_mode: str = Field(alias="from")
    to_mode: str = Field(alias="to")


class HITLGateOpened(WSEventBase):
    type: Literal[WSEventType.HITL_GATE_OPENED] = WSEventType.HITL_GATE_OPENED
    task_id: UUID
    gate: dict[str, Any]
    preview_artifact: dict[str, Any]


class AgentStatusChanged(WSEventBase):
    type: Literal[WSEventType.AGENT_STATUS_CHANGED] = WSEventType.AGENT_STATUS_CHANGED
    agent_id: str
    status: Literal["working", "idle", "fishing", "training"]


WSEvent = (
    StepStarted
    | StepCompleted
    | StepStreaming
    | WorkModeChanged
    | HITLGateOpened
    | AgentStatusChanged
)
