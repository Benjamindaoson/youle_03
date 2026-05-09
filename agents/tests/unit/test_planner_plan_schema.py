"""Plan schema 单测(ADR-019)。

覆盖:
- 合法 plan 通过 pydantic 校验
- 非法 agent / 重复 step_id / 缺失 dep / primary_artifact 不存在 → 报错
- to_skill_yaml() 产物 shape 与 compiler.build_state_graph 期望一致
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.orchestrator_agent.planner.plan_schema import (
    HITLGateSpec,
    Plan,
    PlanStep,
    PlanValidationError,
)


def _ok_step(sid: str, deps: list[str] | None = None, **overrides):
    base = {
        "step_id": sid,
        "agent": "agent_1",
        "task_type": "web_search",
        "persona": "default",
        "depends_on": deps or [],
        "timeout": 60,
        "prompt_template": "",
        "inputs": {},
        "parameters": {},
        "routing_hints": {},
        "mcp_tools": [],
    }
    base.update(overrides)
    return PlanStep(**base)


def _ok_plan(*, steps=None, primary=None) -> Plan:
    steps = steps or [_ok_step("a"), _ok_step("b", deps=["a"])]
    return Plan(
        plan_id="p-001",
        rationale="test",
        steps=steps,
        primary_artifact=primary,
    )


def test_valid_plan_passes() -> None:
    plan = _ok_plan()
    plan.validate_deps()
    assert len(plan.steps) == 2
    assert plan.steps[0].step_id == "a"
    assert plan.source == "planner"


def test_duplicate_step_id_rejected() -> None:
    with pytest.raises((ValidationError, PlanValidationError)):
        Plan(
            plan_id="p-dup",
            steps=[_ok_step("a"), _ok_step("a")],
        )


def test_invalid_agent_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanStep(
            step_id="x",
            agent="agent_5",  # 只有 1..4
            task_type="web_search",
        )


def test_missing_dep_rejected() -> None:
    plan = Plan(
        plan_id="p-miss",
        steps=[_ok_step("a", deps=["nonexistent"])],
    )
    with pytest.raises(PlanValidationError):
        plan.validate_deps()


def test_primary_artifact_must_exist() -> None:
    plan = _ok_plan(primary="z_missing")
    with pytest.raises(PlanValidationError):
        plan.validate_deps()


def test_to_skill_yaml_shape() -> None:
    plan = _ok_plan(
        steps=[
            _ok_step("a", routing_hints={"primary": "kimi-k2"}, mcp_tools=["mcp://search/web_search"]),
            _ok_step(
                "b",
                deps=["a"],
                hitl_gate=HITLGateSpec(type="version_select", timeout_seconds=600),
                expected_artifact="copy",
                budget_tokens=4000,
                persona="researcher",
            ),
        ],
        primary="b",
    )
    plan.validate_deps()
    sy = plan.to_skill_yaml()

    # 顶层字段对齐 build_state_graph 的解析点
    assert sy["skill_id"] == "dynamic-p-001"
    assert sy["version"] == "dynamic-1.0"
    assert sy["delivery"]["primary_artifact"] == "b"
    assert sy["_dynamic"] is True
    assert sy["_planner_meta"]["plan_id"] == "p-001"

    # workflow item shape
    assert len(sy["workflow"]) == 2
    a, b = sy["workflow"]
    assert a["step_id"] == "a"
    assert a["agent"] == "agent_1"
    assert a["task_type"] == "web_search"
    assert a["mcp_tools"] == ["mcp://search/web_search"]
    assert a["routing_hints"] == {"primary": "kimi-k2"}

    # ADR-019 新增字段下传到 parameters._planner(react_runner 可见)
    assert a["parameters"]["_planner"]["plan_id"] == "p-001"
    assert b["parameters"]["_planner"]["persona"] == "researcher"
    assert b["parameters"]["_planner"]["budget_tokens"] == 4000
    assert b["parameters"]["_planner"]["expected_artifact"] == "copy"

    # HITL gate 转译为 dict
    assert b["hitl_gate"]["type"] == "version_select"
    assert b["hitl_gate"]["timeout_seconds"] == 600


def test_step_persona_defaults_to_default() -> None:
    s = PlanStep(step_id="x", agent="agent_2", task_type="pptx_assemble")
    assert s.persona == "default"


def test_steps_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        Plan(plan_id="empty", steps=[])
