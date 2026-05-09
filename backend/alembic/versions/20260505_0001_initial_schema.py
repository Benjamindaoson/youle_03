"""initial schema — 18+ 张表(对齐 docs/5_工程基建/V1 工程基建清单.md §4)

Revision ID: 0001
Revises:
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 扩展(若 docker-init 已建则幂等)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("nickname", sa.String(50)),
        sa.Column("avatar_url", sa.Text),
        sa.Column("avatar_style", sa.String(50)),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", postgresql.TIMESTAMP(timezone=True)),
    )

    # 2. user_preferences
    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preferences", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("preference_vec", postgresql.JSONB),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # 3. skills(conversations 引用,先建;v4 已删除独立 context_pools 表,Brief 直接挂 conversations.brief)
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", sa.String(100), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("domain", sa.String(20)),
        sa.Column("scenario", sa.String(50), index=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("creator_type", sa.String(20), server_default="platform"),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True)),
        sa.Column("visibility", sa.String(20), server_default="public"),
        sa.Column("keywords", postgresql.ARRAY(sa.String), server_default=sa.text("ARRAY[]::TEXT[]")),
        sa.Column("anti_signals", postgresql.ARRAY(sa.String), server_default=sa.text("ARRAY[]::TEXT[]")),
        sa.Column("yaml_content", sa.Text, nullable=False),
        sa.Column("inputs_schema", postgresql.JSONB),
        sa.Column("workflow_steps", postgresql.JSONB),
        sa.Column("status", sa.String(20), server_default="published"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_skills_keywords", "skills", ["keywords"], postgresql_using="gin")
    op.create_index("idx_skills_anti_signals", "skills", ["anti_signals"], postgresql_using="gin")

    # 4. conversations(v4:brief 直接挂在这里,不再用 context_pools 表)
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("work_mode", sa.String(10)),  # plan/ask/auto, v3.0 ADR-014
        sa.Column("avatar_style", sa.String(50)),
        sa.Column(
            "brief",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{\"完成度\": 0.0, \"字段\": {}, \"决策日志\": []}'::jsonb"),
        ),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id")),
        sa.Column("private_chat_agent_id", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_message_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("mode IN ('main_session','group','private_chat')", name="conv_mode_chk"),
        sa.CheckConstraint("work_mode IN ('plan','ask','auto') OR work_mode IS NULL", name="conv_work_mode_chk"),
        sa.CheckConstraint("status IN ('active','paused','archived','deleted')", name="conv_status_chk"),
    )
    op.create_index("idx_conv_user_mode", "conversations", ["user_id", "mode"])
    op.execute(
        "CREATE INDEX idx_conv_user_work_mode ON conversations(user_id, work_mode) WHERE mode='group'"
    )
    op.execute(
        "CREATE INDEX idx_conv_last_msg ON conversations(user_id, last_message_at DESC NULLS LAST)"
    )

    # 6. mode_switch_log(v3.0 ADR-014)
    op.create_table(
        "mode_switch_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("from_mode", sa.String(10)),
        sa.Column("to_mode", sa.String(10)),
        sa.Column("triggered_by", sa.String(20)),
        sa.Column("triggered_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX idx_mode_switch_conv ON mode_switch_log(conversation_id, triggered_at DESC)"
    )

    # 7. messages
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("content_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_msg_conv_created", "messages", ["conversation_id", "created_at"])

    # 8. skill_embeddings
    op.create_table(
        "skill_embeddings",
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id"),
            primary_key=True,
        ),
        sa.Column("description_vec", postgresql.JSONB, nullable=False),
    )

    # 9. user_skill_visibility
    op.create_table(
        "user_skill_visibility",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_usv_user", "user_skill_visibility", ["user_id"])

    # 10. tasks
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id")),
        sa.Column("skill_version", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("collected_fields", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "progress",
            postgresql.JSONB,
            server_default=sa.text("'{\"current\": 0, \"total\": 0}'::jsonb"),
        ),
        sa.Column("estimated_duration_seconds", sa.Integer),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("error_detail", postgresql.JSONB),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_tasks_user_status", "tasks", ["user_id", "status"])
    op.create_index("idx_tasks_conv", "tasks", ["conversation_id"])

    # 11. task_steps
    op.create_table(
        "task_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(20)),
        sa.Column("task_type", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("model_used", sa.String(100)),
        sa.Column("output_artifact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error_detail", postgresql.JSONB),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("task_id", "step_id", name="uq_task_step"),
    )
    op.create_index("idx_step_task", "task_steps", ["task_id"])

    # 12. artifacts
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("source_step_id", sa.String(50)),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("is_reference", sa.Boolean, server_default=sa.text("false")),
        sa.Column("is_final", sa.Boolean, server_default=sa.text("false")),
        sa.Column("reference", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_artifact_user", "artifacts", ["user_id"])
    op.create_index("idx_artifact_source", "artifacts", ["source_conversation_id"])
    op.create_index("idx_artifact_task", "artifacts", ["source_task_id"])

    # 13. quota_usage
    op.create_table(
        "quota_usage",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quota_type", sa.String(30), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("consumed", sa.BigInteger, server_default="0"),
        sa.Column("last_used_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "quota_type", "period", name="uq_quota"),
    )
    op.create_index("idx_quota_lookup", "quota_usage", ["user_id", "quota_type", "period"])

    # 14. bgm_library
    op.create_table(
        "bgm_library",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(100)),
        sa.Column("mood", sa.String(30), nullable=False),
        sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("bpm", sa.Integer),
        sa.Column("oss_ref", sa.Text, nullable=False),
        sa.Column("license", sa.String(50)),
        sa.Column("usage_count", sa.BigInteger, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX idx_bgm_mood_duration ON bgm_library(mood, duration) WHERE is_active = TRUE"
    )

    # 15. hitl_gates(ADR-010)
    op.create_table(
        "hitl_gates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(50), nullable=False),
        sa.Column("gate_type", sa.String(30), nullable=False),
        sa.Column("opened_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("timeout_seconds", sa.Integer, server_default="600"),
        sa.Column("resolution", sa.String(20)),
        sa.Column("user_choice", postgresql.JSONB),
        sa.Column("preview_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id")),
        sa.Column("metadata", postgresql.JSONB),
    )
    op.create_index("idx_hitl_task", "hitl_gates", ["task_id"])
    op.execute("CREATE INDEX idx_hitl_open ON hitl_gates(task_id) WHERE closed_at IS NULL")

    # 16. workflow_traces(ADR-011 信号 1)
    op.create_table(
        "workflow_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id")),
        sa.Column("skill_version", sa.String(20)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("user_satisfaction", sa.SmallInteger),
        sa.Column("failure_reason", sa.Text),
        sa.Column("trace_oss_ref", sa.Text),
        sa.Column("qdrant_point_id", sa.Text),
        sa.Column("rollback_count", sa.SmallInteger, server_default="0"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_trace_user_skill", "workflow_traces", ["user_id", "skill_id"])
    op.execute(
        "CREATE INDEX idx_trace_satisfaction ON workflow_traces(user_satisfaction) WHERE user_satisfaction IS NOT NULL"
    )

    # 17. prompt_improvement_candidates(ADR-011 信号 3)
    op.create_table(
        "prompt_improvement_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prompt_name", sa.String(100), nullable=False),
        sa.Column("failure_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("root_cause", sa.Text),
        sa.Column("section_to_improve", sa.Text),
        sa.Column("current_text", sa.Text),
        sa.Column("proposed_changes", postgresql.JSONB),
        sa.Column("expected_improvement", sa.Text),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX idx_pic_pending ON prompt_improvement_candidates(prompt_name) WHERE status = 'pending'"
    )

    # 18. skill_drafts(ADR-011 信号 4 — V1.5)
    op.create_table(
        "skill_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("draft_yaml", sa.Text, nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("submitted_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("reviewed_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("review_notes", sa.Text),
        sa.Column("published_skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id")),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_drafts_user", "skill_drafts", ["user_id", "status"])

    # 19. agent_status(ADR-015)
    op.create_table(
        "agent_status",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("agent_id", sa.String(20), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_active_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # 20. emotion_signals(ADR-015 可选)
    op.create_table(
        "emotion_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(20), nullable=False),
        sa.Column("emotion", sa.String(30)),
        sa.Column("triggered_by", sa.String(50)),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX idx_emotion_user ON emotion_signals(user_id, created_at DESC)")


def downgrade() -> None:
    for tbl in [
        "emotion_signals",
        "agent_status",
        "skill_drafts",
        "prompt_improvement_candidates",
        "workflow_traces",
        "hitl_gates",
        "bgm_library",
        "quota_usage",
        "artifacts",
        "task_steps",
        "tasks",
        "user_skill_visibility",
        "skill_embeddings",
        "messages",
        "mode_switch_log",
        "conversations",
        "skills",
        "user_preferences",
        "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
