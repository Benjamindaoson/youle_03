"""主编排消息管线：在消息落库之后按固定顺序尝试短路。

本模块是 `POST /conversations/{id}/messages` 的决策核心；HTTP 层负责鉴权、配额闸门、
写库与副作用（Brief 防抖、记忆滚动摘要任务）。

**PHASE_ORDER**（与现网行为一致，勿随意调整顺序）：

1. ``mention_shortcut`` — 群内单 @ 非总裁助理 → 私聊式回复
2. ``mode_switch`` — 群 + work_mode 下模式切换检测（I 类）
3. ``private_chat`` — 私聊会话直出
4. ``intent`` — ContextPack + working 记忆 + ``understand_intent``
5. ``support_agents`` — 主会话 HR / 财务短路
6. ``interrupt`` — 任务中断 A/B/E/F/G/H/I
7. ``clarification_answer`` — 多轮澄清续轮或启动任务
8. ``non_task_chitchat`` — 非 task_request
9. ``plan_discussion`` — Plan/Ask 不落任务配额时的讨论回复
10. ``skill_match`` — Skill 匹配、校验、首轮澄清或建任务启动 runner
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import structlog
import yaml as _yaml_module
from agents.orchestrator_agent.clarification import MAX_CLARIFICATION_ROUNDS, generate_clarification
from agents.orchestrator_agent.input_validator import validate_inputs
from agents.orchestrator_agent.intent import understand_intent
from agents.orchestrator_agent.interrupt import (
    InterruptClassification,
    classify_interrupt,
    handle_interrupt,
)
from agents.orchestrator_agent.mode_manager import consumes_task_quota, detect_mode_switch
from agents.orchestrator_agent.runner_factory import make_runner
from agents.orchestrator_agent.skill_match import match_skill
from fastapi import HTTPException, status
from sqlalchemy import select as _sel_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.prompts import PLAN_MODE_DISCUSSION_PROMPT
from app.db import SessionLocal
from app.models.conversation import Conversation
from app.models.hitl_gate import HITLGate
from app.models.message import Message
from app.models.task import Task
from app.models.user import User
from app.models.user_preference import UserPreference
from app.redis_client import get_redis
from app.router import complete
from app.schemas.send_message import SendMessageRequest, SendMessageResponse
from app.schemas.ws import WSEventType
from app.services.brief_builder import merge_brief_into_skill_inputs
from app.services.flywheel import auto_apply_from_preferences
from app.services.memory import build_intent_memory_context
from app.services.quota_enforce import QuotaExceeded, enforce_task_creation, infer_task_kind
from app.services.skill_loader import load_skill_by_id
from app.services.support_agent import finance_respond, hr_respond, route_support_agent
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

_CLARIF_KEY = "clarif:{}:{}"  # format(user_id, conv_id)
_CLARIF_TTL = 600  # 10 分钟

_MENTION_TARGETS_GROUP = {"ceo_assistant", "agent_1", "agent_2", "agent_3", "agent_4"}
_MENTION_TARGETS_MAIN = _MENTION_TARGETS_GROUP | {"hr", "finance_manager"}

_DISPLAY_TO_ID: dict[str, str] = {
    "总裁助理": "ceo_assistant",
    "研究员": "agent_1",
    "文档专员": "agent_2",
    "设计师": "agent_3",
    "影音师": "agent_4",
    "HR": "hr",
    "财务经理": "finance_manager",
}


async def _publish_clarification_ws(
    conv: Conversation,
    *,
    skill_id: str,
    clarification: dict[str, object] | None,
    round_num: int,
    total_missing: int,
) -> None:
    try:
        await ws_manager.publish(
            str(conv.user_id),
            {
                "type": WSEventType.CLARIFICATION_REQUIRED,
                "conversation_id": str(conv.id),
                "skill_id": skill_id,
                "clarification": clarification,
                "round": round_num,
                "total_missing": total_missing,
            },
        )
    except Exception as e:
        log.warning("send_message_handlers.clarification_ws_failed", err=str(e))


async def _run_task_background(task_id: UUID) -> None:
    async with SessionLocal() as session:
        try:
            runner = make_runner(session)
            await runner.start(task_id)
        except Exception:
            log.exception("send_message_handlers.bg_task_failed", task_id=str(task_id))


async def _rerun_current_step(task_id: UUID, instruction: str) -> None:
    async with SessionLocal() as session:
        try:
            open_gate = (
                await session.execute(
                    _sel_task(HITLGate)
                    .where(HITLGate.task_id == task_id, HITLGate.closed_at.is_(None))
                    .order_by(HITLGate.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if open_gate is None:
                log.warning("send_message_handlers.rerun_no_open_gate", task_id=str(task_id))
                return
            runner = make_runner(session)
            await runner.rollback_to_step(
                task_id,
                target_step_id=open_gate.step_id,
                instruction=instruction,
            )
        except Exception:
            log.exception("send_message_handlers.rerun_failed", task_id=str(task_id))


async def _generate_plan_discussion(user_message: str, *, memory_context: str = "") -> str:
    extra = ""
    if memory_context.strip():
        extra = f"【本会话记忆上下文】\n{memory_context.strip()[:1400]}\n\n"
    try:
        resp = await complete(
            task_type="chitchat",
            messages=[
                {"role": "system", "content": extra + PLAN_MODE_DISCUSSION_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.5,
            max_tokens=150,
        )
        return resp.content.strip()
    except Exception as e:
        log.warning("send_message_handlers.plan_discussion_failed", err=str(e))
        return ""


async def _create_and_launch_task(
    *,
    session: AsyncSession,
    conv: Conversation,
    user: User,
    user_msg: Message,
    skill_db_id: UUID,
    skill_yaml_id: str,
    skill_yaml: dict[str, Any],
    collected_fields: dict[str, Any],
) -> SendMessageResponse:
    active = (
        await session.execute(
            _sel_task(Task)
            .where(
                Task.conversation_id == conv.id,
                Task.status.in_(["pending", "running", "paused"]),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is not None:
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="task_conflict",
            payload={
                "active_task_id": str(active.id),
                "options": [
                    {"key": "queue", "label": "排队等候"},
                    {"key": "cancel_current", "label": "取消当前"},
                    {"key": "new_group", "label": "新建群做新的"},
                ],
            },
        )

    try:
        await enforce_task_creation(
            session,
            user=user,
            work_mode=conv.work_mode,
            task_kind=infer_task_kind(skill_yaml),
        )
    except QuotaExceeded as e:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": e.code, "detail": e.detail},
        ) from e

    task = Task(
        id=uuid4(),
        user_id=conv.user_id,
        conversation_id=conv.id,
        skill_id=skill_db_id,
        skill_version=str(skill_yaml.get("version", "1.0")),
        status="pending",
        collected_fields=collected_fields,
        progress={"current": 0, "total": len(skill_yaml.get("workflow", []))},
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    asyncio.create_task(_run_task_background(task.id))

    log.info("send_message_handlers.task_started", task_id=str(task.id), skill=skill_yaml_id)
    return SendMessageResponse(
        message_id=user_msg.id,
        decision="task_started",
        payload={
            "task_id": str(task.id),
            "skill_id": skill_yaml_id,
            "step_count": len(skill_yaml.get("workflow", [])),
        },
    )


async def _execute_interrupt_action(
    action: str,
    *,
    classification: InterruptClassification,
    session: AsyncSession,
    conv: Conversation,
    user_msg: Message,
    active_task: Task | None,
    user_message: str,
) -> SendMessageResponse:
    if action == "pause_task":
        if active_task and active_task.status not in ("paused", "completed", "cancelled", "failed"):
            active_task.status = "paused"
            await session.commit()
            await ws_manager.publish(
                str(conv.user_id),
                {
                    "type": WSEventType.CONVERSATION_STATUS_CHANGED,
                    "conversation_id": str(conv.id),
                    "status": "task_paused",
                    "task_id": str(active_task.id),
                },
            )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="interrupt_handled",
            payload={"action": "pause_task", "task_id": str(active_task.id) if active_task else None},
        )

    if action == "cancel_task":
        if active_task and active_task.status not in ("completed", "cancelled", "failed"):
            active_task.status = "cancelled"
            await session.commit()
            from app.services.agent_cancel import publish_agent_task_cancel

            await publish_agent_task_cancel(active_task.id)
            await ws_manager.publish(
                str(conv.user_id),
                {
                    "type": WSEventType.TASK_FAILED,
                    "task_id": str(active_task.id),
                    "reason": "user_cancelled",
                },
            )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="interrupt_handled",
            payload={"action": "cancel_task", "task_id": str(active_task.id) if active_task else None},
        )

    if action == "merge_brief":
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="interrupt_handled",
            payload={"action": "merge_brief"},
        )

    if action == "store_feedback":
        try:
            redis = await get_redis()
            await redis.xadd(
                "flywheel:signals",
                {
                    "type": "feedback",
                    "payload": json.dumps(
                        {
                            "user_id": str(conv.user_id),
                            "conversation_id": str(conv.id),
                            "task_id": str(active_task.id) if active_task else None,
                            "feedback_text": user_message[:1000],
                        },
                        ensure_ascii=False,
                    ),
                },
            )
        except Exception as e:
            log.warning("send_message_handlers.store_feedback_failed", err=str(e))
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="interrupt_handled",
            payload={"action": "store_feedback"},
        )

    if action == "rerun_step":
        if active_task:
            asyncio.create_task(_rerun_current_step(active_task.id, user_message))
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="interrupt_handled",
            payload={"action": "rerun_step", "task_id": str(active_task.id) if active_task else None},
        )

    if action == "switch_mode":
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="chitchat",
            payload={"action": "switch_mode", "interrupt_class": classification.interrupt_class},
        )

    return SendMessageResponse(
        message_id=user_msg.id,
        decision="chitchat",
        payload={"interrupt_class": classification.interrupt_class},
    )


def _parse_mentions(content: str, hint: list[str]) -> list[str]:
    if hint:
        seen: set[str] = set()
        out: list[str] = []
        for m in hint:
            if m in _MENTION_TARGETS_MAIN and m not in seen:
                seen.add(m)
                out.append(m)
        return out
    out2: list[str] = []
    for display, aid in _DISPLAY_TO_ID.items():
        if f"@{display}" in content and aid not in out2:
            out2.append(aid)
    return out2


def _load_skill_yaml(skill_yaml_id: str, skill_orm: Any | None = None) -> dict[str, Any]:
    try:
        return load_skill_by_id(skill_yaml_id)
    except KeyError:
        if skill_orm is not None:
            return _yaml_module.safe_load(skill_orm.yaml_content)
        raise


async def _phase_mention_shortcut(
    *,
    session: AsyncSession,
    conv: Conversation,
    body: SendMessageRequest,
    user_msg: Message,
    parsed_mentions: list[str],
) -> SendMessageResponse | None:
    if (
        len(parsed_mentions) == 1
        and parsed_mentions[0] != "ceo_assistant"
        and conv.mode in ("main_session", "group")
    ):
        target = parsed_mentions[0]
        allowed = _MENTION_TARGETS_MAIN if conv.mode == "main_session" else _MENTION_TARGETS_GROUP
        if target in allowed:
            from app.services.private_chat import private_chat_respond

            reply = await private_chat_respond(
                session,
                conversation_id=conv.id,
                agent_id=target,
                user_message=body.content,
            )
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="mention_replied",
                payload={"target": target, "reply_message_id": str(reply.id)},
            )
    return None


async def _phase_mode_switch(
    *,
    session: AsyncSession,
    conv: Conversation,
    user_msg: Message,
    body: SendMessageRequest,
) -> SendMessageResponse | None:
    if conv.mode == "group" and conv.work_mode is not None:
        sig = await detect_mode_switch(
            current_mode=conv.work_mode,  # type: ignore[arg-type]
            conversation_name=conv.name,
            message=body.content,
        )
        if sig.switch_to and sig.switch_to != conv.work_mode and sig.confidence >= 0.7:
            old_mode = conv.work_mode
            conv.work_mode = sig.switch_to
            await session.commit()
            await ws_manager.publish(
                str(conv.user_id),
                {
                    "type": WSEventType.WORK_MODE_CHANGED,
                    "conversation_id": str(conv.id),
                    "from": old_mode,
                    "to": sig.switch_to,
                },
            )
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="mode_switched",
                payload={"from": old_mode, "to": sig.switch_to},
            )
    return None


async def _phase_private_chat(
    *,
    session: AsyncSession,
    conv: Conversation,
    body: SendMessageRequest,
    user_msg: Message,
) -> SendMessageResponse | None:
    if conv.mode == "private_chat":
        from app.services.private_chat import private_chat_respond

        reply = await private_chat_respond(
            session,
            conversation_id=conv.id,
            agent_id=conv.private_chat_agent_id or "ceo_assistant",
            user_message=body.content,
        )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="private_chat_replied",
            payload={"role": conv.private_chat_agent_id, "reply_message_id": str(reply.id)},
        )
    return None


async def dispatch_send_message(
    *,
    session: AsyncSession,
    conv: Conversation,
    user: User,
    body: SendMessageRequest,
    user_msg: Message,
    parsed_mentions: list[str],
) -> SendMessageResponse:
    r = await _phase_mention_shortcut(
        session=session, conv=conv, body=body, user_msg=user_msg, parsed_mentions=parsed_mentions
    )
    if r is not None:
        return r

    r = await _phase_mode_switch(session=session, conv=conv, user_msg=user_msg, body=body)
    if r is not None:
        return r

    r = await _phase_private_chat(session=session, conv=conv, body=body, user_msg=user_msg)
    if r is not None:
        return r

    try:
        memory_ctx = await build_intent_memory_context(session, conv, body.content)
    except Exception as e:
        log.warning("send_message_handlers.memory_context_failed", err=str(e))
        memory_ctx = conv.memory_rolling_summary or ""

    intent = await understand_intent(
        user_message=body.content,
        conversation_context={
            "work_mode": conv.work_mode,
            "memory_summary": memory_ctx,
        },
    )

    if conv.mode == "main_session":
        support_role = route_support_agent(intent.intent_type, body.content)
        if support_role == "hr":
            reply = await hr_respond(session, conversation_id=conv.id, user_message=body.content)
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="support_agent_replied",
                payload={"role": "hr", "reply_message_id": str(reply.id)},
            )
        if support_role == "finance":
            plan = user.plan or "free"
            reply = await finance_respond(
                session,
                conversation_id=conv.id,
                user_id=conv.user_id,
                user_message=body.content,
                plan=plan,
            )
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="support_agent_replied",
                payload={"role": "finance", "reply_message_id": str(reply.id)},
            )

    if intent.intent_type == "interrupt":
        active_for_interrupt = (
            await session.execute(
                _sel_task(Task)
                .where(
                    Task.conversation_id == conv.id,
                    Task.status.in_(["executing", "pending", "paused"]),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        task_state_snap: dict[str, Any] = {}
        if active_for_interrupt:
            task_state_snap = {
                "task_id": str(active_for_interrupt.id),
                "status": active_for_interrupt.status,
            }

        classification = await classify_interrupt(
            message=body.content,
            current_task_state=task_state_snap,
        )
        action = await handle_interrupt(classification, task_state=task_state_snap)
        if action == "v2_deferred":
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="chitchat",
                payload={
                    "reason": "v2_only",
                    "interrupt_class": classification.interrupt_class,
                    "message": f"中断 {classification.interrupt_class}(回滚/改方向)将在 V2 支持",
                },
            )
        return await _execute_interrupt_action(
            action,
            classification=classification,
            session=session,
            conv=conv,
            user_msg=user_msg,
            active_task=active_for_interrupt,
            user_message=body.content,
        )

    if intent.intent_type == "clarification_answer":
        redis = await get_redis()
        ctx_raw = await redis.get(_CLARIF_KEY.format(user.id, conv.id))
        if ctx_raw:
            ctx = json.loads(ctx_raw)
            new_collected = {**ctx["collected"], **(intent.entities or {})}
            skill_yaml_ctx = _load_skill_yaml(ctx["skill_yaml_id"])
            validation = validate_inputs(
                inputs_schema=skill_yaml_ctx.get("inputs_schema", []),
                collected_fields=new_collected,
            )

            if validation.is_complete or ctx["round"] >= MAX_CLARIFICATION_ROUNDS - 1:
                await redis.delete(_CLARIF_KEY.format(user.id, conv.id))
                return await _create_and_launch_task(
                    session=session,
                    conv=conv,
                    user=user,
                    user_msg=user_msg,
                    skill_db_id=UUID(ctx["skill_db_id"]),
                    skill_yaml_id=ctx["skill_yaml_id"],
                    skill_yaml=skill_yaml_ctx,
                    collected_fields=validation.filled_fields,
                )

            next_round = ctx["round"] + 1
            clar = generate_clarification(validation.missing_fields, round_number=next_round)
            await redis.setex(
                _CLARIF_KEY.format(user.id, conv.id),
                _CLARIF_TTL,
                json.dumps({
                    "skill_yaml_id": ctx["skill_yaml_id"],
                    "skill_db_id": ctx["skill_db_id"],
                    "collected": new_collected,
                    "round": next_round,
                }),
            )
            log.info(
                "send_message_handlers.clarification_next_round",
                conv_id=str(conv.id),
                round=next_round,
                field=clar.field if clar else None,
            )
            clar_dump = clar.model_dump() if clar else None
            await _publish_clarification_ws(
                conv,
                skill_id=ctx["skill_yaml_id"],
                clarification=clar_dump,
                round_num=next_round,
                total_missing=len(validation.missing_fields),
            )
            return SendMessageResponse(
                message_id=user_msg.id,
                decision="clarification_required",
                payload={
                    "skill_id": ctx["skill_yaml_id"],
                    "clarification": clar_dump,
                    "round": next_round,
                    "total_missing": len(validation.missing_fields),
                },
            )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="chitchat",
            payload={"intent": intent.model_dump()},
        )

    if intent.intent_type != "task_request":
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="chitchat",
            payload={"intent": intent.model_dump()},
        )

    if not consumes_task_quota(conv.work_mode):  # type: ignore[arg-type]
        ai_reply = await _generate_plan_discussion(body.content, memory_context=memory_ctx)
        plan_msg: Message | None = None
        if ai_reply:
            from app.services.conversation import append_message

            plan_msg = await append_message(
                session,
                conversation_id=conv.id,
                role="ceo_assistant",
                content=ai_reply,
            )
            await ws_manager.publish(
                str(conv.user_id),
                {
                    "type": WSEventType.MESSAGE_ADDED,
                    "conversation_id": str(conv.id),
                    "message": {
                        "id": str(plan_msg.id),
                        "role": "ceo_assistant",
                        "content": ai_reply,
                        "kind": "plan_discussion",
                    },
                },
            )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="plan_discussion",
            payload={
                "work_mode": conv.work_mode,
                "reply_message_id": str(plan_msg.id) if plan_msg else None,
            },
        )

    skill = await match_skill(
        session=session,
        user_message=body.content,
        intent=intent.model_dump(),
        memory_context=memory_ctx,
    )
    if skill is None:
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="chitchat",
            payload={"reason": "no_skill_matched", "intent": intent.model_dump()},
        )

    skill_yaml = _load_skill_yaml(skill.skill_id, skill)

    schema = skill_yaml.get("inputs_schema", [])
    pref_row = await session.get(UserPreference, conv.user_id)
    pref_filled = auto_apply_from_preferences(
        prefs=(pref_row.preferences if pref_row else {}) or {},
        schema=schema,
    )
    brief_filled = merge_brief_into_skill_inputs(
        brief=conv.brief or {}, inputs_schema=schema
    )
    collected = {**pref_filled, **brief_filled, **(intent.entities or {})}

    validation = validate_inputs(
        inputs_schema=skill_yaml.get("inputs_schema", []),
        collected_fields=collected,
    )
    if not validation.is_complete:
        clar = generate_clarification(validation.missing_fields, round_number=0)
        redis = await get_redis()
        await redis.setex(
            _CLARIF_KEY.format(user.id, conv.id),
            _CLARIF_TTL,
            json.dumps({
                "skill_yaml_id": skill.skill_id,
                "skill_db_id": str(skill.id),
                "collected": collected,
                "round": 0,
            }),
        )
        log.info(
            "send_message_handlers.clarification_started",
            conv_id=str(conv.id),
            skill=skill.skill_id,
            missing=[f["name"] for f in validation.missing_fields],
        )
        clar_dump = clar.model_dump() if clar else None
        await _publish_clarification_ws(
            conv,
            skill_id=skill.skill_id,
            clarification=clar_dump,
            round_num=0,
            total_missing=len(validation.missing_fields),
        )
        return SendMessageResponse(
            message_id=user_msg.id,
            decision="clarification_required",
            payload={
                "skill_id": skill.skill_id,
                "clarification": clar_dump,
                "round": 0,
                "total_missing": len(validation.missing_fields),
            },
        )

    return await _create_and_launch_task(
        session=session,
        conv=conv,
        user=user,
        user_msg=user_msg,
        skill_db_id=skill.id,
        skill_yaml_id=skill.skill_id,
        skill_yaml=skill_yaml,
        collected_fields=validation.filled_fields,
    )
