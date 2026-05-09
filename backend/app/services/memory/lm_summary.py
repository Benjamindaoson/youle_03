"""LLM 驱动的滚动摘要刷新(每 N 条消息触发一次 LLM 重写)。

与 algorithms/rolling_summary.py 中的纯文本拼接互补:
  - 纯文本拼接:任务完成时追加 task card 到摘要末尾(同步,不调 LLM)
  - LLM 重写:每 N 条消息,把最近对话重新压缩为一段连贯摘要(异步,调 LLM)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.redis_client import get_redis
from app.router import complete

log = structlog.get_logger(__name__)

_EVERY_N_MESSAGES = 20
_COUNTER_KEY = "conv_msg_count:{}"
_COUNTER_TTL = 86400
_HISTORY_WINDOW = 40
_MAX_MSG_CHARS = 300
_SUMMARY_MAX_TOKENS = 300


async def maybe_update_rolling_summary(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    every_n: int = _EVERY_N_MESSAGES,
) -> None:
    """消息计数器 +1;每 every_n 条触发一次 LLM 摘要重写。

    设计为非阻塞:失败时只记 warning,不影响主流程。
    """
    try:
        redis = await get_redis()
        key = _COUNTER_KEY.format(conversation_id)
        count = int(await redis.incr(key))
        await redis.expire(key, _COUNTER_TTL)
        if count % every_n != 0:
            return
    except Exception as e:
        log.warning("memory.counter_failed", conv_id=str(conversation_id), err=str(e))
        return

    await _regenerate_summary(session, conversation_id=conversation_id)


async def _regenerate_summary(session: AsyncSession, *, conversation_id: UUID) -> None:
    """拉取最近 N 条消息 → LLM 摘要 → 写回 DB。"""
    try:
        rows = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(_HISTORY_WINDOW)
        )
        msgs = list(reversed(rows.scalars().all()))
        if not msgs:
            return

        history_text = "\n".join(
            f"[{m.role}]: {(m.content or '')[:_MAX_MSG_CHARS]}"
            for m in msgs
            if m.content
        )
        if not history_text.strip():
            return

        resp = await complete(
            task_type="chitchat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是会话摘要助手。请用 100-200 字总结以下对话的:"
                        "用户核心目标、已完成的关键步骤、待决策或待补充的信息。"
                        "输出纯文本,不要 Markdown 标题或列表符号。"
                    ),
                },
                {"role": "user", "content": history_text},
            ],
            temperature=0.2,
            max_tokens=_SUMMARY_MAX_TOKENS,
        )
        summary = (resp.content or "").strip()
        if not summary:
            return

        conv = await session.get(Conversation, conversation_id)
        if conv is not None:
            conv.memory_rolling_summary = summary
            conv.memory_summary_updated_at = datetime.now(UTC)
            await session.commit()
            log.info(
                "memory.lm_summary_updated",
                conv_id=str(conversation_id),
                chars=len(summary),
            )

    except Exception as e:
        log.warning("memory.lm_summary_failed", conv_id=str(conversation_id), err=str(e))
