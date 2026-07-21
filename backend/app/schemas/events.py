"""Canonical contract shared by SSE and WebSocket event transports."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_STATUS_CHANGED = "conversation_status_changed"
    MESSAGE_ADDED = "message_added"
    AGENT_MESSAGE_STARTED = "agent_message_started"
    AGENT_MESSAGE_DELTA = "agent_message_delta"
    AGENT_MESSAGE_COMPLETED = "agent_message_completed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_STREAMING = "step_streaming"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_ROLLED_BACK = "task_rolled_back"
    CLARIFICATION_REQUIRED = "clarification_required"
    MODE_CHOICE_REQUIRED = "mode_choice_required"
    WORK_MODE_CHANGED = "work_mode_changed"
    BRIEF_UPDATED = "brief_updated"
    HITL_GATE_OPENED = "hitl_gate_opened"
    HITL_GATE_CLOSED = "hitl_gate_closed"
    ARTIFACT_ADDED = "artifact_added"
    SKILL_CHANGED = "skill_changed"
    QUOTA_WARNING = "quota_warning"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    ERROR = "error"
    PONG = "pong"


class UserEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EventType
    user_id: UUID
    conversation_id: UUID | None = None
    task_id: UUID | None = None
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
