"""记忆模块 Pydantic 契约 — 供 API 与 prompt 装配。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ArtifactRecallItem(BaseModel):
    artifact_id: UUID
    title: str | None
    summary: str | None
    type: str
    reference_tail: str | None = Field(
        default=None, description="OSS ref 尾部,避免把长 URL 打进 prompt"
    )
    score: float = 0.0


class TaskCardView(BaseModel):
    task_id: UUID
    status: str
    one_liner: str
    skill_id: UUID | None = None
    primary_ref: str | None = None


class MemoryContextPack(BaseModel):
    """总裁助理 / 主编排可消费的统一记忆包(短文本,需再按 token 预算裁剪)。"""

    conversation_id: UUID
    brief_digest: str = ""
    rolling_summary: str = ""
    preference_digest: str = ""
    recent_tasks: list[TaskCardView] = Field(default_factory=list)
    recalled_artifacts: list[ArtifactRecallItem] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
