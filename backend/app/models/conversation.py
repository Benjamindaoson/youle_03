from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Conversation(Base):
    """v3.0 ADR-014:work_mode 字段实现三模式同群切换。

    v4 简化:Brief 直接挂 conversations.brief JSONB,不再用独立 context_pools 表。
    """

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    work_mode: Mapped[str | None] = mapped_column(String(10))  # plan / ask / auto
    avatar_style: Mapped[str | None] = mapped_column(String(50))
    brief: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {"完成度": 0.0, "字段": {}, "决策日志": []},
        nullable=False,
    )
    skill_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skills.id"))
    private_chat_agent_id: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    #: 会话级中期记忆:滚动摘要(v4 memory 模块)
    memory_rolling_summary: Mapped[str | None] = mapped_column(Text)
    memory_summary_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("mode IN ('main_session','group','private_chat')", name="conv_mode_chk"),
        CheckConstraint("work_mode IN ('plan','ask','auto') OR work_mode IS NULL", name="conv_work_mode_chk"),
        CheckConstraint(
            "status IN ('active','paused','archived','deleted')", name="conv_status_chk"
        ),
    )
