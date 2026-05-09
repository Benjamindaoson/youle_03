"""主编排消息链路用的记忆装配 — ContextPack + 短期 working 	slot。"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.services.memory.context_pack import build_memory_context_pack
from app.services.memory.working import working_set

log = structlog.get_logger(__name__)

_INTENT_MEMORY_CAP = 2800


def _format_pack_for_intent(pack: Any) -> str:
    parts: list[str] = []
    if getattr(pack, "brief_digest", "").strip():
        parts.append("【Brief】\n" + pack.brief_digest.strip()[:900])
    if getattr(pack, "rolling_summary", "").strip():
        parts.append("【滚动摘要】\n" + pack.rolling_summary.strip()[:700])
    if getattr(pack, "preference_digest", "").strip():
        parts.append("【用户偏好】\n" + pack.preference_digest.strip()[:400])
    recent = getattr(pack, "recent_tasks", None) or []
    if recent:
        lines = []
        for t in recent[:5]:
            lines.append(f"- {t.status}: {t.one_liner[:160]}")
        parts.append("【近期任务】\n" + "\n".join(lines))
    recalled = getattr(pack, "recalled_artifacts", None) or []
    if recalled:
        lines = []
        for a in recalled[:6]:
            title = a.title or "(无标题)"
            sm = (a.summary or "")[:120]
            lines.append(f"- {title}: {sm}")
        parts.append("【相关产物召回】\n" + "\n".join(lines))
    blob = "\n\n".join(parts)
    if len(blob) > _INTENT_MEMORY_CAP:
        return blob[: _INTENT_MEMORY_CAP] + "…"
    return blob


async def build_intent_memory_context(
    session: AsyncSession,
    conv: Conversation,
    user_message: str,
) -> str:
    """供 `understand_intent` / Plan 讨论注入 system 侧：失败时降级为滚动摘要。"""
    await working_set(
        conv.id,
        "last_user_turn",
        {"content": (user_message or "")[:6000]},
    )
    try:
        q = (user_message or "").strip()[:500] or None
        pack = await build_memory_context_pack(
            session,
            conversation_id=conv.id,
            user_id=conv.user_id,
            recall_query=q,
            task_limit=5,
        )
        return _format_pack_for_intent(pack)
    except Exception as e:
        log.warning("memory.intent_pack_failed", err=str(e), conv_id=str(conv.id))
        return (conv.memory_rolling_summary or "")[: _INTENT_MEMORY_CAP]
