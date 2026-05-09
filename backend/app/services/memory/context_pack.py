"""装配 MemoryContextPack — 中层(Brief/滚动/任务)/长期(检索)合一出口。"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.conversation import Conversation
from app.models.task import Task
from app.models.user_preference import UserPreference
from app.services.memory.algorithms.recall_keywords import rank_artifacts_keyword
from app.services.memory.schemas import ArtifactRecallItem, MemoryContextPack, TaskCardView


def _brief_digest(brief: dict[str, Any] | None, max_chars: int = 2400) -> str:
    if not brief:
        return ""
    try:
        s = json.dumps(brief, ensure_ascii=False)
    except Exception:
        s = str(brief)
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


def _prefs_digest(pref: dict[str, Any], max_chars: int = 800) -> str:
    if not pref:
        return ""
    skip = {"preference_vec"}
    trimmed = {k: v for k, v in pref.items() if k not in skip}
    try:
        s = json.dumps(trimmed, ensure_ascii=False)
    except Exception:
        s = str(trimmed)
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


async def build_memory_context_pack(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    recall_query: str | None = None,
    task_limit: int = 5,
) -> MemoryContextPack:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise ValueError("conversation not found or access denied")

    pref_row = await session.get(UserPreference, user_id)

    rows = (
        await session.execute(
            select(Task)
            .where(Task.conversation_id == conversation_id)
            .order_by(desc(Task.created_at))
            .limit(task_limit)
        )
    ).scalars().all()

    recent: list[TaskCardView] = []
    for t in rows:
        card = t.memory_card or {}
        recent.append(
            TaskCardView(
                task_id=t.id,
                status=t.status,
                one_liner=str(card.get("one_liner") or f"{t.status} …{str(t.id)[:8]}"),
                skill_id=t.skill_id,
                primary_ref=card.get("primary_artifact_ref")
                if isinstance(card.get("primary_artifact_ref"), str)
                else None,
            )
        )

    recalled: list[ArtifactRecallItem] = []
    if recall_query and recall_query.strip():
        arts = (
            await session.execute(
                select(Artifact).where(Artifact.source_conversation_id == conversation_id).limit(200)
            )
        ).scalars().all()
        tuples: list[tuple[str, str | None, str | None, str, str, list[str]]] = []
        for a in arts:
            tg = a.memory_tags if isinstance(a.memory_tags, list) else []
            tuples.append((str(a.id), a.title, a.summary, a.type, a.reference, [str(x) for x in tg]))
        ranked = rank_artifacts_keyword(recall_query, tuples)
        for r in ranked:
            recalled.append(
                ArtifactRecallItem(
                    artifact_id=UUID(r.artifact_id),
                    title=r.title,
                    summary=(r.summary or "")[:500] if r.summary else None,
                    type=r.type,
                    reference_tail=r.reference[-96:] if r.reference else None,
                    score=r.score,
                )
            )

    return MemoryContextPack(
        conversation_id=conversation_id,
        brief_digest=_brief_digest(conv.brief),
        rolling_summary=(conv.memory_rolling_summary or "")[:6000],
        preference_digest=_prefs_digest(pref_row.preferences if pref_row else {}),
        recent_tasks=recent,
        recalled_artifacts=recalled,
        meta={
            "work_mode": conv.work_mode,
            "memory_summary_updated_at": conv.memory_summary_updated_at.isoformat()
            if conv.memory_summary_updated_at
            else None,
            "task_limit": task_limit,
        },
    )
