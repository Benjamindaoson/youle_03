from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas.events import EventType, UserEvent


class UserEventRecord(Base):
    """Append-only durable copy of a user-facing event."""

    __tablename__ = "user_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id")
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    agent_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_user_events_replay",
            "user_id",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    def to_schema(self) -> UserEvent:
        return UserEvent(
            id=self.id,
            type=EventType(self.type),
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            payload=self.payload,
            created_at=self.created_at,
        )
