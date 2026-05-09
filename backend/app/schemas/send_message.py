"""Pydantic models for POST /conversations/{id}/messages."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str
    role: str = "user"
    # 用户在群内 @ 某个 Agent 的 id 列表(铁律 1:用户→Agent 允许;Agent→Agent 禁止)
    mentions: list[str] = []


class SendMessageResponse(BaseModel):
    message_id: UUID
    decision: str  # task_started / clarification_required / chitchat / mode_switched / mention_replied / ...
    payload: dict[str, object] = Field(default_factory=dict)
