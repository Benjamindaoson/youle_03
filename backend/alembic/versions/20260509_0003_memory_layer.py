"""Memory layer columns (中期滚动摘要 / task 履历卡 / artifact 检索字段)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("memory_rolling_summary", sa.Text()),
    )
    op.add_column(
        "conversations",
        sa.Column("memory_summary_updated_at", postgresql.TIMESTAMP(timezone=True)),
    )
    op.add_column(
        "tasks",
        sa.Column("memory_card", postgresql.JSONB, nullable=True),
    )
    op.add_column("artifacts", sa.Column("title", sa.String(512)))
    op.add_column("artifacts", sa.Column("summary", sa.Text()))
    op.add_column(
        "artifacts",
        sa.Column(
            "memory_tags",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("idx_art_conv_created", "artifacts", ["source_conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_art_conv_created", table_name="artifacts")
    op.drop_column("artifacts", "memory_tags")
    op.drop_column("artifacts", "summary")
    op.drop_column("artifacts", "title")
    op.drop_column("tasks", "memory_card")
    op.drop_column("conversations", "memory_summary_updated_at")
    op.drop_column("conversations", "memory_rolling_summary")
