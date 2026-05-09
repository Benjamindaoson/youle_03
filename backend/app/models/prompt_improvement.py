from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PromptImprovementCandidate(Base):
    """ADR-011 信号 3:Reflexion 改进候选。"""

    __tablename__ = "prompt_improvement_candidates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_name: Mapped[str] = mapped_column(String(100), nullable=False)
    failure_task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    root_cause: Mapped[str | None] = mapped_column(Text)
    section_to_improve: Mapped[str | None] = mapped_column(Text)
    current_text: Mapped[str | None] = mapped_column(Text)
    proposed_changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expected_improvement: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
