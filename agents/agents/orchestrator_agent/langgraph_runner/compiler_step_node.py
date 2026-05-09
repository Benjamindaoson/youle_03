"""单步 LangGraph 节点工厂 — 从 compiler 拆分。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from jinja2 import Template
from langgraph.types import interrupt

from agents.orchestrator_agent.langgraph_runner.compiler_templates import (
    hydrate_steps_for_templates,
    render_static_input,
)
from agents.orchestrator_agent.langgraph_runner.critic_node import (
    build_retry_prompt as _critic_build_retry_prompt,
    evaluate as _critic_evaluate,
    get_max_retries as _critic_get_max_retries,
    is_critic_enabled_for as _critic_is_enabled_for,
)
from agents.orchestrator_agent.langgraph_runner.failure_policy import retry_config_for_step
from agents.orchestrator_agent.langgraph_runner.state import TaskState
from app.schemas.agent import AgentTask

log = structlog.get_logger(__name__)

DispatchFn = Callable[[AgentTask], Any]  # async


def make_step_node(
    step_def: dict[str, Any],
    *,
    dispatcher: DispatchFn,
    result_waiter: Callable[[str, str, int], Any],
    failure_handling: dict[str, Any] | None = None,
    md_knowledge_prefix: str = "",
):
    """生成单个 step 节点:内容水合 + 追踪字段 + Skill failure_handling 重试语义。"""

    sid: str = step_def["step_id"]
    agent_id: str = step_def["agent"]
    task_type: str = step_def["task_type"]
    timeout_s: int = int(step_def.get("timeout") or 120)
    has_gate = bool(step_def.get("hitl_gate"))
    gate_cfg = step_def.get("hitl_gate") or {}
    prompt_template: str = step_def.get("prompt_template", "")
    static_inputs: dict[str, Any] = step_def.get("inputs") or {}
    parameters: dict[str, Any] = step_def.get("parameters") or {}
    routing_hints: dict[str, Any] = step_def.get("routing_hints") or {}

    fh = failure_handling or {}
    retry_max, backoff_base = retry_config_for_step(sid, fh)

    md_prefix = (md_knowledge_prefix or "").strip()

    async def _node(state: TaskState) -> dict[str, Any]:
        # 已完成:防 time-travel 后重跑
        prev = (state.get("step_results") or {}).get(sid)
        if prev and prev.get("status") == "completed":
            log.info("lg.node.skip_completed", step_id=sid)
            return {}

        started = datetime.now(UTC).isoformat()
        fields = state.get("collected_fields") or {}
        step_results_map = dict(state.get("step_results") or {})
        tid_str = state["task_id"]
        uuid_task = UUID(tid_str)
        trace_tid = (state.get("trace_id") or "")[:32]
        run_id_str = (state.get("orchestration_run_id") or "").strip()
        if not trace_tid:
            trace_tid = uuid4().hex[:32]
        if not run_id_str:
            run_id_str = tid_str

        state_trace_patch: dict[str, Any] = {}
        if not (state.get("trace_id") or "").strip():
            state_trace_patch["trace_id"] = trace_tid
        if not (state.get("orchestration_run_id") or "").strip():
            state_trace_patch["orchestration_run_id"] = run_id_str

        orch_uuid = UUID(run_id_str)

        tmpl_g: dict[str, Any] = {
            "step_results": step_results_map,
            "orc": {
                "trace_id": trace_tid,
                "run_id": run_id_str,
                "task_id": tid_str,
                "skill_id": state.get("skill_id"),
                "step_id": sid,
            },
        }

        base_ctx = {
            step_id_: {
                "output": res.get("artifact_ref"),
                "reference": res.get("artifact_ref"),
                "artifact_ref": res.get("artifact_ref"),
                "type": res.get("artifact_type"),
                "metadata": res.get("artifact_metadata") or {},
            }
            for step_id_, res in step_results_map.items()
        }
        step_context_h = await hydrate_steps_for_templates(base_ctx, step_results_map)

        inputs = render_static_input(
            static_inputs, fields=fields, step_context=step_context_h, tmpl_globals=tmpl_g
        )
        if prompt_template:
            try:
                inputs["_prompt"] = Template(prompt_template).render(
                    **{**tmpl_g, **fields, **step_context_h}
                )
            except Exception as e:
                log.warning("lg.template_render_failed", step_id=sid, err=str(e))

        if md_prefix:
            inputs["_md_skill_knowledge"] = md_prefix
            pt = inputs.get("_prompt")
            if isinstance(pt, str) and pt.strip():
                inputs["_prompt"] = (
                    "[MD Skill 知识包]\n"
                    + md_prefix
                    + "\n\n---\n\n[本步任务]\n"
                    + pt
                )

        upstream_refs = {
            up_sid: r.get("artifact_ref")
            for up_sid, r in step_results_map.items()
            if r.get("artifact_ref")
        }
        if upstream_refs:
            inputs["_upstream"] = upstream_refs

        parameters_tpl = render_static_input(
            parameters, fields=fields, step_context=step_context_h, tmpl_globals=tmpl_g
        )

        effective_routing: dict[str, Any] = dict(routing_hints)
        dispatch_sent = int((state.get("step_dispatch_counts") or {}).get(sid, 0))
        attempt_idx = 0
        result: Any = None

        while attempt_idx < retry_max:
            p_render = dict(parameters_tpl)
            if attempt_idx > 0:
                ohi = dict(p_render.get("orchestration_hints") or {})
                ohi.update(
                    {
                        "failure_retry": True,
                        "attempt": attempt_idx,
                        "policy": fh.get(sid),
                    }
                )
                p_render["orchestration_hints"] = ohi
                if fh.get(sid, {}).get("on_failure") == "retry_with_different_anchor":
                    fb = effective_routing.get("fallback")
                    prim = effective_routing.get("primary")
                    if isinstance(fb, list) and fb:
                        effective_routing = {
                            **effective_routing,
                            "primary": fb[0],
                            "fallback": fb[1:] + ([prim] if prim is not None else []),
                        }

            agent_task = AgentTask(
                task_id=uuid_task,
                step_id=sid,
                agent_id=agent_id,  # type: ignore[arg-type]
                task_type=task_type,
                user_id=UUID(str(state["user_id"])),
                conversation_id=UUID(str(state["conversation_id"])),
                inputs=dict(inputs),
                parameters=p_render,
                routing_hints=dict(effective_routing),
                skill_id=state.get("skill_id"),
                skill_version=state.get("skill_version"),
                timeout_seconds=timeout_s,
                mcp_tools=list(step_def.get("mcp_tools") or []),
                orchestration_run_id=orch_uuid,
                trace_id=trace_tid or None,
                dispatch_attempt=attempt_idx,
                idempotency_key=f"{run_id_str}:{tid_str}:{sid}:{attempt_idx}",
            )

            await dispatcher(agent_task)
            dispatch_sent += 1
            log.info(
                "lg.dispatched",
                step_id=sid,
                agent=agent_id,
                trace_id=trace_tid,
                run_id=run_id_str,
                attempt=attempt_idx,
            )

            result = await result_waiter(state["task_id"], sid, timeout_s)
            counts_so_far: dict[str, Any] = {"step_dispatch_counts": {sid: dispatch_sent}}

            if result is None:
                log.warning("lg.await_timeout_attempt", step_id=sid, attempt=attempt_idx)
                if attempt_idx + 1 >= retry_max:
                    return {
                        **state_trace_patch,
                        "step_results": {
                            sid: {
                                "step_id": sid,
                                "agent_id": agent_id,
                                "task_type": task_type,
                                "status": "failed",
                                "error_detail": {
                                    "reason": "timeout_after_retries",
                                    "timeout_s": timeout_s,
                                    "attempts": retry_max,
                                },
                                "started_at": started,
                                "completed_at": datetime.now(UTC).isoformat(),
                            }
                        },
                        "final_status": "failed",
                        "failure_reason": f"step {sid!r} timeout after {retry_max} attempts",
                        **counts_so_far,
                    }
                attempt_idx += 1
                await asyncio.sleep(backoff_base ** (attempt_idx))
                continue

            if result.status == "failed":
                log.warning(
                    "lg.worker_failed_attempt",
                    step_id=sid,
                    trace_id=trace_tid,
                    err=result.error_detail,
                    attempt=attempt_idx,
                )
                if attempt_idx + 1 >= retry_max:
                    completed = datetime.now(UTC).isoformat()
                    step_result = {
                        "step_id": sid,
                        "agent_id": agent_id,
                        "task_type": task_type,
                        "status": result.status,
                        "artifact_ref": result.output.reference if result.output else None,
                        "artifact_type": result.output.type if result.output else None,
                        "artifact_metadata": (result.output.extra_metadata if result.output else {})
                        or {},
                        "duration_ms": result.duration_ms,
                        "cost_usd": float(result.cost_usd) if result.cost_usd is not None else None,
                        "model_used": result.model_used,
                        "error_detail": result.error_detail,
                        "started_at": started,
                        "completed_at": completed,
                    }
                    return {
                        **state_trace_patch,
                        "step_results": {sid: step_result},
                        "final_status": "failed",
                        "failure_reason": (result.error_detail or {}).get("reason")
                        or f"step {sid} failed",
                        **counts_so_far,
                    }
                attempt_idx += 1
                await asyncio.sleep(backoff_base ** attempt_idx)
                continue

            break

        assert result is not None

        counts_patch_final: dict[str, Any] = {"step_dispatch_counts": {sid: dispatch_sent}}

        _backoff = 5.0
        _max_backoff = float(os.getenv("ORCH_EXTERNAL_POLL_MAX_BACKOFF", "30"))
        while result.status == "pending_external":
            log.info(
                "lg.pending_external",
                step_id=sid,
                external_workflow_id=result.external_workflow_id,
            )
            await asyncio.sleep(_backoff)
            _backoff = min(_backoff * 2, _max_backoff)
            result = await result_waiter(state["task_id"], sid, timeout_s)
            if result is None:
                log.error("lg.external_timeout", step_id=sid, timeout=timeout_s)
                return {
                    **state_trace_patch,
                    "step_results": {
                        sid: {
                            "step_id": sid,
                            "agent_id": agent_id,
                            "task_type": task_type,
                            "status": "failed",
                            "error_detail": {
                                "reason": "external_timeout",
                                "timeout_s": timeout_s,
                            },
                            "started_at": started,
                            "completed_at": datetime.now(UTC).isoformat(),
                        }
                    },
                    "final_status": "failed",
                    "failure_reason": f"step {sid!r} external workflow timeout",
                    **counts_patch_final,
                }

        # ── ADR-020:Critic Loop(默认关 — ENABLE_CRITIC_LOOP) ──
        # 创作类 step 后接 critic 评审,不达阈值则带反馈重派一次。
        # critic 自身故障 / 非文本产物 → CritiqueResult.passed()=True,主流程不阻塞。
        critique_meta: dict[str, Any] | None = None
        if result.status == "completed" and _critic_is_enabled_for(task_type, step_def):
            from agents.orchestrator_agent.langgraph_runner.artifact_body import (
                fetch_artifact_text_excerpt,
            )

            max_critic_retries = _critic_get_max_retries(step_def)
            rendered_prompt_for_critic: str = (
                inputs.get("_prompt") if isinstance(inputs.get("_prompt"), str) else ""
            ) or prompt_template
            critic_attempt = 0
            while critic_attempt < max_critic_retries:
                # 取产物文本(只对文本类有效;图像/视频会在 evaluate 内被跳过)
                artifact_text_for_critic = ""
                artifact_type_for_critic = (
                    result.output.type if result.output else None
                )
                if result.output and result.output.reference:
                    try:
                        excerpt = await fetch_artifact_text_excerpt(
                            reference=str(result.output.reference),
                            artifact_type=artifact_type_for_critic,
                        )
                        artifact_text_for_critic = excerpt.get("text") or ""
                    except Exception as e:
                        log.warning(
                            "lg.critic.fetch_fail",
                            step_id=sid,
                            err=str(e)[:200],
                        )
                        break

                critique = await _critic_evaluate(
                    step_def=step_def,
                    task_type=task_type,
                    rendered_prompt=rendered_prompt_for_critic,
                    produced_artifact_text=artifact_text_for_critic,
                    produced_artifact_type=artifact_type_for_critic,
                    collected_fields=fields,
                )
                critique_meta = critique.to_dict()
                log.info(
                    "lg.critic.evaluated",
                    step_id=sid,
                    score=critique.score,
                    threshold=critique.threshold_used,
                    passed=critique.passed(),
                    attempt=critic_attempt,
                    skipped=critique.skipped_reason,
                )

                if critique.passed() or not critique.should_retry:
                    break

                # 评审未过且建议重试 → 改写 prompt + 带反馈重派
                new_prompt = _critic_build_retry_prompt(
                    original_prompt=rendered_prompt_for_critic,
                    critique=critique,
                )
                new_inputs = dict(agent_task.inputs)
                new_inputs["_prompt"] = new_prompt
                new_inputs["_critic_feedback"] = critique.feedback_summary()
                agent_task = agent_task.model_copy(
                    update={
                        "inputs": new_inputs,
                        "dispatch_attempt": agent_task.dispatch_attempt + 1,
                        "idempotency_key": (
                            f"{run_id_str}:{tid_str}:{sid}:c{critic_attempt + 1}"
                        ),
                    }
                )
                await dispatcher(agent_task)
                dispatch_sent += 1
                log.info(
                    "lg.critic.redispatch",
                    step_id=sid,
                    critic_attempt=critic_attempt,
                    score=critique.score,
                )

                new_result = await result_waiter(state["task_id"], sid, timeout_s)
                if new_result is None or new_result.status != "completed":
                    log.warning(
                        "lg.critic.retry_no_result",
                        step_id=sid,
                        critic_attempt=critic_attempt,
                        new_status=getattr(new_result, "status", None),
                    )
                    break  # 让步:保留上一轮结果
                result = new_result
                rendered_prompt_for_critic = new_prompt
                critic_attempt += 1
            counts_patch_final = {"step_dispatch_counts": {sid: dispatch_sent}}

        completed = datetime.now(UTC).isoformat()
        step_result = {
            "step_id": sid,
            "agent_id": agent_id,
            "task_type": task_type,
            "status": result.status,
            "artifact_ref": result.output.reference if result.output else None,
            "artifact_type": result.output.type if result.output else None,
            "artifact_metadata": (result.output.extra_metadata if result.output else {}) or {},
            "duration_ms": result.duration_ms,
            "cost_usd": float(result.cost_usd) if result.cost_usd is not None else None,
            "model_used": result.model_used,
            "error_detail": result.error_detail,
            "started_at": started,
            "completed_at": completed,
            "critique": critique_meta,
        }

        update: dict[str, Any] = {
            **state_trace_patch,
            **counts_patch_final,
            "step_results": {sid: step_result},
        }

        # ─── HITL gate:中断,等用户决议 ───
        if has_gate and result.status == "completed":
            if os.getenv("YOULE_AUTO_APPROVE_HITL", "").lower() in {"1", "true", "yes"}:
                update["hitl_decisions"] = {
                    sid: {
                        "resolution": "approved",
                        "feedback": "auto approved by YOULE_AUTO_APPROVE_HITL",
                    }
                }
                return update
            decision = interrupt(
                {
                    "kind": "hitl_gate",
                    "step_id": sid,
                    "gate_type": gate_cfg.get("gate_type") or gate_cfg.get("type", "quality_review"),
                    "timeout_seconds": gate_cfg.get("timeout_seconds"),
                    "preview_artifact_ref": step_result["artifact_ref"],
                    "preview_artifact_type": step_result["artifact_type"],
                    "preview_artifact_metadata": step_result["artifact_metadata"],
                    "task_id": state["task_id"],
                    "agent_id": agent_id,
                    "trace_id": trace_tid,
                    "orchestration_run_id": run_id_str,
                }
            )
            # 用户回复:{"resolution": "approved" | "modify_request" | "rejected", "feedback": "..."}
            update["hitl_decisions"] = {sid: decision}
            if decision.get("resolution") == "rejected":
                update["final_status"] = "failed"
                update["failure_reason"] = f"HITL {sid} rejected: {decision.get('feedback', '')[:200]}"

        return update

    _node.__name__ = f"step_{sid}"
    return _node
