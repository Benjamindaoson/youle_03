"""LangGraph runner / ingest 钩子 — 记忆失败不打断主编排。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

from app.models.artifact import Artifact
from app.models.conversation import Conversation
from app.models.task import Task
from app.services.memory.algorithms.artifact_profile import derive_artifact_profile
from app.services.memory.algorithms.rolling_summary import merge_rolling_summary
from app.services.memory.algorithms.task_card import build_task_memory_card, format_task_card_log_line

log = structlog.get_logger(__name__)


def enrich_artifact_inline(artifact: Artifact) -> None:
    """在 flush/commit 前原地补全检索字段。"""
    try:
        title, summary, tags = derive_artifact_profile(
            artifact_type=artifact.type,
            reference=artifact.reference,
            metadata=dict(artifact.extra_metadata or {}),
        )
        if artifact.title is None:
            artifact.title = title
        if artifact.summary is None:
            artifact.summary = summary
        if not artifact.memory_tags:
            artifact.memory_tags = tags
    except Exception as e:
        log.warning("memory.enrich_artifact_failed", err=str(e), artifact_id=str(artifact.id))


def apply_task_memory_snapshot(
    *,
    task: Task,
    conv: Conversation | None,
    state: dict[str, Any],
) -> None:
    """同一次事务内写 task.memory_card + 会话滚动摘要。"""
    try:
        card = build_task_memory_card(task=task, state=state)
        task.memory_card = card
        if conv is not None:
            line = format_task_card_log_line(card)
            conv.memory_rolling_summary = merge_rolling_summary(conv.memory_rolling_summary, line)
            conv.memory_summary_updated_at = datetime.now(UTC)
    except Exception as e:
        log.warning("memory.apply_task_snapshot_failed", err=str(e), task_id=str(task.id))
