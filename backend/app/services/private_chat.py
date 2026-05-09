"""私聊会话(v4 §237-240):用户与单个 Agent 直对话。

约束(v4 #238 / #240):
- 不启动完整 Skill 工作流
- 不调度其他 Agent
- 响应快(短上下文 + 直接 LLM 调用)
- 仍可调用单 Agent 的轻量 Skill(本实现暂只走 LLM)
- 私聊历史与群聊互不污染(由 conversation_id 隔离天然实现)
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.prompts import (
    AGENT1_SHORT_WRITING_PROMPT,
    FINANCE_SYSTEM_PROMPT,
    HR_SYSTEM_PROMPT,
)
from app.models.message import Message
from app.router import complete
from app.services.conversation import append_message

log = structlog.get_logger(__name__)


# 简化的角色 → 系统提示词
PRIVATE_PROMPTS: dict[str, str] = {
    "hr": HR_SYSTEM_PROMPT,
    "finance_manager": FINANCE_SYSTEM_PROMPT,
    "agent_1": AGENT1_SHORT_WRITING_PROMPT,
    "agent_2": "你是文档专员,擅长 Excel/Word/PDF/长图拼接。私聊响应要轻、要快。",
    "agent_3": "你是设计师,擅长 文生图/批量生成/风格分析。私聊响应要轻、要快。",
    "agent_4": "你是影音师,擅长 TTS/Whisper/BGM/视频合成。私聊响应要轻、要快。",
    "ceo_assistant": "你是用户的总裁助理,在私聊里更直接、不调度团队,只用一两句帮 ta 想清楚。",
}


async def private_chat_respond(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    agent_id: str,
    user_message: str,
) -> Message:
    """单 Agent 直对话 → 写一条 Message 回去。"""
    sys_prompt = PRIVATE_PROMPTS.get(agent_id, PRIVATE_PROMPTS["ceo_assistant"])

    history_rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(8)
        )
    ).scalars().all()
    history = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content or ""}
        for m in reversed(history_rows)
        if m.content
    ]
    messages = [{"role": "system", "content": sys_prompt}, *history, {"role": "user", "content": user_message}]

    resp = await complete(
        task_type="intent_understanding",
        messages=messages,
        temperature=0.6,
        max_tokens=350,
    )
    log.info("private_chat.respond", agent_id=agent_id, conversation_id=str(conversation_id))
    return await append_message(
        session,
        conversation_id=conversation_id,
        role=agent_id,
        content=resp.content,
        extra_metadata={"private_chat": True},
    )
