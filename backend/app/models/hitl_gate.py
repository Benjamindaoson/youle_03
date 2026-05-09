from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HITLGate(Base):
    """ADR-010:Hero 任务 HITL gate。"""

    __tablename__ = "hitl_gates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(50), nullable=False)
    gate_type: Mapped[str] = mapped_column(String(30), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600)
    resolution: Mapped[str | None] = mapped_column(String(20))
    user_choice: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    preview_artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
