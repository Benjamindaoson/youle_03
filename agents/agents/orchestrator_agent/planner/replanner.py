"""Replanner — 失败/HITL 修改/偏航时重新规划(ADR-019)。

S1 阶段:**骨架 + 单元测试就绪**,但默认未挂到 failure_policy。
S2 阶段:接通 failure_policy.py,在重试耗尽时调起 replanner 而不是直接 fail。

Replan 时的关键约束:
1. 已完成 step 的 step_id **必须保留** — LangGraph state 里这些 step 已是
   completed,dynamic_compiler 翻成 skill_yaml 后,runner 自动跳过(compiler.py
   的 `_node` 第 142 行已有 skip_completed 逻辑)。
2. Replan 次数有上限(默认 ≤ 2),超过即任务 fail。
3. `source="replanner"`,便于飞轮信号区分 plan vs replan。
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog
from pydantic import ValidationError as PydanticValidationError

from agents._common.llm import LITELLM_MOCK, complete_cognitive
from agents.orchestrator_agent.planner.plan_schema import (
    Plan,
    PlanValidationError,
)
from agents.orchestrator_agent.planner.planner_agent import (
    PlannerError,
    _extract_json,
    _PlanParseError,
)
from agents.orchestrator_agent.planner.prompts import (
    REPLANNER_SYSTEM_PROMPT,
    render_replanner_user_prompt,
)

log = structlog.get_logger(__name__)

REPLANNER_MAX_REPLANS = int(os.getenv("REPLANNER_MAX_REPLANS", "2"))


async def replan(
    *,
    original_plan: Plan,
    failed_step_id: str,
    failure_detail: dict[str, Any] | str,
    completed_step_results: dict[str, dict[str, Any]],
    replan_attempt: int = 0,
) -> Plan:
    """根据失败重新规划。

    Args:
        original_plan: 上一份 Plan
        failed_step_id: 失败的 step_id
        failure_detail: 错误信息(可以是 dict 或 string)
        completed_step_results: 已完成 step 的 step_results 子集(从 TaskState 取)
        replan_attempt: 第几次 replan(由 failure_policy 计数)

    Raises:
        PlannerError: 超过 REPLANNER_MAX_REPLANS 次或 LLM 输出始终无效。
    """
    if replan_attempt >= REPLANNER_MAX_REPLANS:
        raise PlannerError(
            f"replan_attempt={replan_attempt} ≥ REPLANNER_MAX_REPLANS={REPLANNER_MAX_REPLANS}"
        )

    completed_refs = _format_completed_refs(completed_step_results)
    failure_str = (
        json.dumps(failure_detail, ensure_ascii=False)
        if isinstance(failure_detail, dict)
        else str(failure_detail)
    )

    user_prompt = render_replanner_user_prompt(
        original_plan_json=original_plan.model_dump_json(indent=2),
        failed_step_id=failed_step_id,
        failure_detail=failure_str,
        completed_step_refs=completed_refs,
    )

    if LITELLM_MOCK:
        # mock:把原 plan 标记为 replanner,把失败 step 的 timeout 翻倍
        new_plan = original_plan.model_copy(deep=True)
        new_plan.source = "replanner"
        new_plan.rationale = f"[MOCK replan] failed step={failed_step_id}, doubling timeout"
        for s in new_plan.steps:
            if s.step_id == failed_step_id:
                s.timeout = min(s.timeout * 2, 3600)
        new_plan.validate_deps()
        return new_plan

    resp = await complete_cognitive(
        purpose="replanner",
        messages=[
            {"role": "system", "content": REPLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=4000,
    )

    raw = resp.content.strip()
    try:
        parsed = _extract_json(raw)
    except _PlanParseError as e:
        log.warning("replanner.parse_fail", err=str(e)[:300])
        raise PlannerError(f"replanner produced unparseable JSON: {e}") from e

    parsed["source"] = "replanner"
    parsed.setdefault("cognitive_model", resp.model)

    try:
        new_plan = Plan(**parsed)
        new_plan.validate_deps()
    except (PydanticValidationError, PlanValidationError) as e:
        log.warning("replanner.invalid_plan", err=str(e)[:300])
        raise PlannerError(f"replanner produced invalid Plan: {e}") from e

    log.info(
        "replanner.replan_ok",
        plan_id=new_plan.plan_id,
        steps=len(new_plan.steps),
        failed_step=failed_step_id,
        attempt=replan_attempt,
    )
    return new_plan


def _format_completed_refs(completed: dict[str, dict[str, Any]]) -> str:
    if not completed:
        return "(无已完成 step)"
    out = []
    for sid, r in completed.items():
        if r.get("status") != "completed":
            continue
        out.append(
            f"- step_id: {sid}\n"
            f"  artifact_ref: {r.get('artifact_ref')}\n"
            f"  artifact_type: {r.get('artifact_type')}"
        )
    return "\n".join(out) if out else "(无已完成 step)"
