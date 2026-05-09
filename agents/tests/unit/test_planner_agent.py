"""Planner Agent 单测(ADR-019)。

LITELLM_MOCK=true 下走 _mock_plan() 路径,无网络依赖。
覆盖:
- make_plan() 在 mock 下返回合法 Plan
- entry.plan_and_compile() 端到端跑通
- subagent.spawn() mock 路径正常
- replanner.replan() mock 路径修改 timeout
- is_dynamic_plan_enabled() 默认 false
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agents.orchestrator_agent.planner.entry import (
    is_dynamic_plan_enabled,
    plan_and_compile,
)
from agents.orchestrator_agent.planner.plan_schema import Plan
from agents.orchestrator_agent.planner.planner_agent import make_plan
from agents.orchestrator_agent.planner.replanner import replan
from agents.orchestrator_agent.planner.subagent import (
    Subagent,
    SubagentBudgetExceededError,
)


async def _noop_dispatch(task):
    return None


async def _noop_wait(task_id, step_id, timeout):
    return None


def test_dynamic_plan_disabled_by_default(monkeypatch) -> None:
    # 必须默认关 — 生产链路才安全
    monkeypatch.delenv("ENABLE_DYNAMIC_PLAN", raising=False)
    assert is_dynamic_plan_enabled() is False


def test_dynamic_plan_enable_via_env(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_DYNAMIC_PLAN", "true")
    assert is_dynamic_plan_enabled() is True
    monkeypatch.setenv("ENABLE_DYNAMIC_PLAN", "1")
    assert is_dynamic_plan_enabled() is True
    monkeypatch.setenv("ENABLE_DYNAMIC_PLAN", "false")
    assert is_dynamic_plan_enabled() is False


@pytest.mark.asyncio
async def test_make_plan_mock_returns_valid_plan() -> None:
    plan = await make_plan(
        user_request="给我做一个反诈短视频",
        user_id="user-001",
    )
    assert isinstance(plan, Plan)
    assert len(plan.steps) >= 1
    plan.validate_deps()
    # mock 给出 research → script
    sids = {s.step_id for s in plan.steps}
    assert "research" in sids
    assert "script" in sids


@pytest.mark.asyncio
async def test_plan_and_compile_end_to_end() -> None:
    plan, skill_yaml, builder = await plan_and_compile(
        user_request="给我做一个反诈短视频",
        user_id="user-002",
        dispatcher=_noop_dispatch,
        result_waiter=_noop_wait,
    )
    # plan 有效
    assert isinstance(plan, Plan)
    plan.validate_deps()
    # skill_yaml 是 dict 且含 _dynamic 标记
    assert skill_yaml["_dynamic"] is True
    assert skill_yaml["_planner_meta"]["plan_id"] == plan.plan_id
    # builder 有 step 节点
    nodes = set(builder.nodes.keys())
    assert "planner" in nodes
    assert "finalize" in nodes
    assert any(n.startswith("step_") for n in nodes)


@pytest.mark.asyncio
async def test_replan_mock_doubles_timeout() -> None:
    plan = await make_plan(user_request="x", user_id="u")
    failed_step = plan.steps[1].step_id  # "script"
    original_timeout = plan.steps[1].timeout

    new_plan = await replan(
        original_plan=plan,
        failed_step_id=failed_step,
        failure_detail={"reason": "model timeout"},
        completed_step_results={
            plan.steps[0].step_id: {
                "status": "completed",
                "artifact_ref": "oss://mock",
                "artifact_type": "text",
            }
        },
        replan_attempt=0,
    )
    assert new_plan.source == "replanner"
    new_failed = next(s for s in new_plan.steps if s.step_id == failed_step)
    assert new_failed.timeout == min(original_timeout * 2, 3600)


@pytest.mark.asyncio
async def test_replan_max_attempts_enforced() -> None:
    plan = await make_plan(user_request="x", user_id="u")
    from agents.orchestrator_agent.planner.planner_agent import PlannerError

    with pytest.raises(PlannerError):
        await replan(
            original_plan=plan,
            failed_step_id=plan.steps[0].step_id,
            failure_detail="dummy",
            completed_step_results={},
            replan_attempt=99,  # 超过上限
        )


# ─── subagent ───
class _Critique(BaseModel):
    score: float = 0.0
    issues: list[str] = []
    should_replan: bool = False


@pytest.mark.asyncio
async def test_subagent_spawn_mock_with_schema() -> None:
    result = await Subagent.spawn(
        goal="评估 artifact 质量",
        persona="critic",
        inputs={"artifact_text": "..."},
        return_schema=_Critique,
    )
    assert result.status == "completed"
    assert result.depth == 0
    # mock 路径返回的是 schema 默认值字典
    assert isinstance(result.output, dict)


@pytest.mark.asyncio
async def test_subagent_spawn_mock_no_schema() -> None:
    result = await Subagent.spawn(goal="自由文本任务", persona="default")
    assert result.status == "completed"
    assert isinstance(result.output, str)


@pytest.mark.asyncio
async def test_subagent_depth_limit() -> None:
    with pytest.raises(SubagentBudgetExceededError):
        await Subagent.spawn(
            goal="too deep",
            depth=99,
        )


@pytest.mark.asyncio
async def test_subagent_budget_hard_cap() -> None:
    with pytest.raises(SubagentBudgetExceededError):
        await Subagent.spawn(
            goal="too greedy",
            budget_tokens=99_999,
        )
