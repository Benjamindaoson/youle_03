from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ModeSwitchLog(Base):
    """v3.0 ADR-014 审计:模式切换历史。"""

    __tablename__ = "mode_switch_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    from_mode: Mapped[str | None] = mapped_column(String(10))
    to_mode: Mapped[str | None] = mapped_column(String(10))
    triggered_by: Mapped[str | None] = mapped_column(String(20))
    triggered_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
