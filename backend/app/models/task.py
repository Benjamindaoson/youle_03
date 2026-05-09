from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    skill_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skills.id"))
    skill_version: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    collected_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=lambda: {"current": 0, "total": 0}
    )
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Task 履历卡 — 摘要化 episodic,serv long-term recall / UX
    memory_card: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: LangGraph state 镜像 — 排障与跨系统 trace 对齐
    orchestration_run_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(20))
    task_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    model_used: Mapped[str | None] = mapped_column(String(100))
    output_artifact_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (UniqueConstraint("task_id", "step_id", name="uq_task_step"),)
