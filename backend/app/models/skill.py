from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    skill_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(20))
    scenario: Mapped[str | None] = mapped_column(String(50), index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    creator_type: Mapped[str] = mapped_column(String(20), default="platform")
    creator_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    anti_signals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    inputs_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    workflow_steps: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="published")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkillEmbedding(Base):
    __tablename__ = "skill_embeddings"

    skill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    description_vec: Mapped[list[float]] = mapped_column(JSONB, nullable=False)


class UserSkillVisibility(Base):
    __tablename__ = "user_skill_visibility"

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    skill_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skills.id"))
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "skill_id"),
        CheckConstraint(
            "relationship IN ('installed_enabled','installed_disabled')",
            name="user_skill_relationship_chk",
        ),
    )
