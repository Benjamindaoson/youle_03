"""retire the legacy topic-specific video skill

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE skills SET status = 'archived', visibility = 'private' "
        "WHERE skill_id = 'anti_fraud_video'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE skills SET status = 'published', visibility = 'public' "
        "WHERE skill_id = 'anti_fraud_video'"
    )
