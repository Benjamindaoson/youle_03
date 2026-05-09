from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AgentStatus(Base):
    """ADR-015 拟人化:每用户每 Agent 当前工作状态。"""

    __tablename__ = "agent_status"

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    agent_id: Mapped[str] = mapped_column(String(20))  # agent_1..4 / hr / finance_manager
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    __table_args__ = (PrimaryKeyConstraint("user_id", "agent_id"),)
