from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SkillDraft(Base):
    """ADR-011 信号 4:创作者飞轮(V1.5 上线)。"""

    __tablename__ = "skill_drafts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    source_task_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.id"))
    draft_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    published_skill_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("skills.id")
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
