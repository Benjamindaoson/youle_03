from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WorkflowTrace(Base):
    """ADR-011 信号 1:工作流完整轨迹(Postgres 镜像 + Qdrant 向量)。"""

    __tablename__ = "workflow_traces"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id"), unique=True
    )
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    skill_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skills.id"))
    skill_version: Mapped[str | None] = mapped_column(String(20))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    user_satisfaction: Mapped[int | None] = mapped_column(SmallInteger)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    trace_oss_ref: Mapped[str | None] = mapped_column(Text)
    qdrant_point_id: Mapped[str | None] = mapped_column(Text)
    rollback_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
