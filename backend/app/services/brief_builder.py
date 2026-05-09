"""Brief 构建器(v4 §15 + 铁律 6)。

升级点(Package F):
- 从 DB 加载初始 brief(conversations.brief JSONB)
- flush 后持久化回 DB
- 推送 WS BRIEF_UPDATED 事件
- 完成度 ≥ 0.8 时建议切到 Auto(自动写一条互动消息提醒)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any
from uuid import UUID

import structlog

from app.db import SessionLocal as async_session_factory  # noqa: N813
from app.models.conversation import Conversation
from agents.orchestrator_agent.mode_manager import update_brief
from app.schemas.ws import WSEventType
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

BRIEF_AUTO_THRESHOLD = 0.8


class BriefDebouncer:
    """对每个 conversation_id 做防抖批量更新。"""

    def __init__(self, *, silence_seconds: float = 5.0, batch_size: int = 3) -> None:
        self._buffers: dict[UUID, list[dict[str, str]]] = defaultdict(list)
        self._timers: dict[UUID, asyncio.Task[None]] = {}
        self._silence = silence_seconds
        self._batch = batch_size
        self._lock = asyncio.Lock()

    async def push(self, conversation_id: UUID, message: dict[str, str]) -> None:
        async with self._lock:
            self._buffers[conversation_id].append(message)
            if len(self._buffers[conversation_id]) >= self._batch:
                await self._flush(conversation_id)
                return
            if conversation_id in self._timers:
                self._timers[conversation_id].cancel()
            self._timers[conversation_id] = asyncio.create_task(
                self._delayed_flush(conversation_id)
            )

    async def _delayed_flush(self, conversation_id: UUID) -> None:
        try:
            await asyncio.sleep(self._silence)
            async with self._lock:
                await self._flush(conversation_id)
        except asyncio.CancelledError:
            pass

    async def _flush(self, conversation_id: UUID) -> None:
        msgs = self._buffers.pop(conversation_id, [])
        self._timers.pop(conversation_id, None)
        if not msgs:
            return
        async with async_session_factory() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None:
                log.warning("brief.flush.no_conversation", conversation_id=str(conversation_id))
                return
            current = dict(conv.brief or {"完成度": 0.0, "字段": {}, "决策日志": []})
            try:
                updated = await update_brief(current_brief=current, new_messages=msgs)
            except Exception as e:
                log.warning("brief.flush_failed", err=str(e))
                return

            conv.brief = updated
            await session.commit()

            await ws_manager.publish(
                str(conv.user_id),
                {
                    "type": WSEventType.BRIEF_UPDATED,
                    "conversation_id": str(conversation_id),
                    "brief": updated,
                },
            )

            score = float(updated.get("完成度", 0.0) or 0.0)
            if score >= BRIEF_AUTO_THRESHOLD and conv.work_mode == "plan":
                await ws_manager.publish(
                    str(conv.user_id),
                    {
                        "type": WSEventType.MODE_CHOICE_REQUIRED,
                        "conversation_id": str(conversation_id),
                        "suggestion": "auto",
                        "reason": "brief_complete",
                        "score": score,
                    },
                )
            log.info(
                "brief.flushed",
                conversation_id=str(conversation_id),
                score=score,
                msg_count=len(msgs),
            )


brief_debouncer = BriefDebouncer()


# ── Plan → Auto 字段填充(v4 #136 / #145)──
def merge_brief_into_skill_inputs(
    *, brief: dict[str, Any], inputs_schema: list[dict[str, Any]]
) -> dict[str, Any]:
    """切到 Auto 时,把 Brief 字段映射到 Skill 的 inputs 上。

    匹配规则(简单到复杂):
    1. 字段 name 完全相同 → 取
    2. 字段 name 中文同义(如"年份"/"年度")→ 取
    3. brief.字段 中没有 → 跳过(由后续 clarification 处理)
    """
    filled: dict[str, Any] = {}
    brief_fields = (brief or {}).get("字段") or {}
    aliases: dict[str, list[str]] = {
        "年份": ["年度", "year", "年"],
        "骗局类型": ["诈骗类型", "scam_type", "骗局"],
        "受众": ["目标人群", "audience", "群体"],
        "商品类型": ["品类", "product_type"],
        "风格": ["视觉风格", "style"],
    }
    for sch in inputs_schema:
        name = sch.get("name")
        if not name:
            continue
        if name in brief_fields:
            filled[name] = brief_fields[name]
            continue
        for canonical, alts in aliases.items():
            if name in (canonical, *alts) and canonical in brief_fields:
                filled[name] = brief_fields[canonical]
                break
    return filled
