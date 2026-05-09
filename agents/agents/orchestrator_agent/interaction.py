"""子模块 9:Agent 互动编排器(v3.0 ADR-015,铁律 22 第 8 子模块)。

V1 克制策略 — 不每步演戏:
  - 仅在「上一 step 的 Agent ≠ 当前 step 的 Agent」时触发(真发生交接)
  - 单 Skill 任务最多 N 次互动消息(默认 3)避免刷屏
  - 严肃场景(金融/医疗/政务)关闭演戏

调用入口(LangGraph step_node 完成时调):
  await emit_and_persist_handoff(
      session, conversation_id, user_id,
      from_agent="agent_1", to_agent="agent_3",
      summary="调研报告写完了,现在出图"
  )

写一条 messages 表 + 推 WS message_added 事件,前端按"互动消息"样式渲染。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.prompts import AGENT_HANDOFF_PROMPT
from app.models.message import Message
from app.router import complete
from app.schemas.ws import WSEventType
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

AGENT_DISPLAY = {
    "ceo_assistant": "总裁助理",
    "agent_1": "研究员",
    "agent_2": "文档专员",
    "agent_3": "设计师",
    "agent_4": "影音师",
    "hr": "HR",
    "finance_manager": "财务经理",
}

SOLEMN_SCENARIOS = {"finance", "medical", "government"}

# 单 Skill 任务互动消息上限(防刷屏 / 防成本失控)
MAX_HANDOFFS_PER_TASK = 3


async def emit_handoff(
    *,
    from_agent: str,
    to_agent: str,
    summary: str,
    scenario: str | None = None,
) -> str:
    """LLM 生成一句 Agent 间交接的群聊语;严肃场景返回空串。

    纯文本生成,不写库 / 不推 WS — 用于单测 + 给上层调用方组装消息。
    """
    if scenario in SOLEMN_SCENARIOS:
        return ""

    try:
        resp = await complete(
            task_type="chitchat",  # handoff 文案生成:轻量创意文本,复用 chitchat 路由
            messages=[
                {
                    "role": "system",
                    "content": AGENT_HANDOFF_PROMPT.format(
                        from_agent=AGENT_DISPLAY.get(from_agent, from_agent),
                        to_agent=AGENT_DISPLAY.get(to_agent, to_agent),
                        summary=summary[:200],
                    ),
                }
            ],
            temperature=0.5,
            max_tokens=80,
        )
        return resp.content.strip()
    except Exception as e:
        log.warning("interaction.emit_handoff_failed", err=str(e))
        return ""


async def emit_and_persist_handoff(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    from_agent: str,
    to_agent: str,
    summary: str,
    scenario: str | None = None,
    task_id: UUID | None = None,
) -> Message | None:
    """V1 真入口:生成 handoff 文本 → 写 messages 表 → 推 WS message_added。

    返回写入的 Message,或 None(严肃场景 / LLM 失败 / 文本空)。
    """
    text = await emit_handoff(
        from_agent=from_agent, to_agent=to_agent, summary=summary, scenario=scenario
    )
    if not text:
        return None

    msg = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=from_agent,
        content=text,
        content_type="text",
        extra_metadata={
            "kind": "interaction",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task_id": str(task_id) if task_id else None,
        },
    )
    session.add(msg)
    await session.commit()

    try:
        await ws_manager.publish(
            str(user_id),
            {
                "type": WSEventType.MESSAGE_ADDED,
                "conversation_id": str(conversation_id),
                "message": {
                    "id": str(msg.id),
                    "conversation_id": str(conversation_id),
                    "role": from_agent,
                    "kind": "interaction",
                    "text": text,
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                },
            },
        )
    except Exception as e:
        log.warning("interaction.ws_publish_failed", err=str(e))

    log.info(
        "interaction.handoff_emitted",
        from_agent=from_agent,
        to_agent=to_agent,
        conv=str(conversation_id),
        task_id=str(task_id) if task_id else None,
    )
    return msg


# ── LangGraph 节点完成时调用的判断器(避免每步都演戏)──
def should_emit_handoff(
    *,
    prev_agent: str | None,
    current_agent: str,
    handoffs_so_far: int,
    scenario: str | None = None,
) -> bool:
    """判断当前 step 完成后是否触发互动消息。

    - prev_agent is None(第 1 个 step)→ 不触发(没人可交接)
    - prev_agent == current_agent → 不触发(同 Agent 连续步骤,内部细节不演)
    - handoffs_so_far >= MAX_HANDOFFS_PER_TASK → 不触发(防刷屏)
    - scenario in SOLEMN_SCENARIOS → 不触发
    """
    if scenario in SOLEMN_SCENARIOS:
        return False
    if prev_agent is None or prev_agent == current_agent:
        return False
    return handoffs_so_far < MAX_HANDOFFS_PER_TASK
