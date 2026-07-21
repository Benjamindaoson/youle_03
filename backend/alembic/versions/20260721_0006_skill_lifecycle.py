"""normalize per-user Skill lifecycle

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE user_skill_visibility "
        "SET relationship = 'installed_enabled' "
        "WHERE relationship <> 'installed_disabled'"
    )
    op.add_column(
        "user_skill_visibility",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "user_skill_relationship_chk",
        "user_skill_visibility",
        "relationship IN ('installed_enabled','installed_disabled')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "user_skill_relationship_chk",
        "user_skill_visibility",
        type_="check",
    )
    op.drop_column("user_skill_visibility", "updated_at")
    op.execute(
        "UPDATE user_skill_visibility "
        "SET relationship = 'subscribed' "
        "WHERE relationship = 'installed_enabled'"
    )
