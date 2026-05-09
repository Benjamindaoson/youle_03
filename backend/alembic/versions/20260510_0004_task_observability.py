"""task 可观测性字段 — orchestration_run_id / trace_id

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("orchestration_run_id", sa.String(36)))
    op.add_column("tasks", sa.Column("trace_id", sa.String(64)))


def downgrade() -> None:
    op.drop_column("tasks", "trace_id")
    op.drop_column("tasks", "orchestration_run_id")
