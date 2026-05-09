"""dynamic_compiler 单测(ADR-019)。

核心断言:
1. Plan → skill_yaml → build_state_graph 全链路通,产出和 YAML 路径相同的
   StateGraphBuilder(节点、边、router 完整)。
2. plan_to_skill_yaml() 产物可被 compile_to_dag 校验通过(环检测共用)。
3. 非法 plan(环 / 缺 dep)在 build_state_graph_from_plan 早 fail。
"""

from __future__ import annotations

import pytest

from agents.orchestrator_agent.langgraph_runner.dynamic_compiler import (
    build_state_graph_from_plan,
    plan_to_skill_yaml,
)
from agents.orchestrator_agent.planner.plan_schema import (
    HITLGateSpec,
    Plan,
    PlanStep,
    PlanValidationError,
)
from agents.orchestrator_agent.task_compiler import DAGCompileError, compile_to_dag


async def _noop_dispatch(task):
    return None


async def _noop_wait(task_id, step_id, timeout):
    return None


def _step(sid, deps=None, **overrides):
    base = dict(
        step_id=sid,
        agent="agent_1",
        task_type="web_search",
        depends_on=deps or [],
    )
    base.update(overrides)
    return PlanStep(**base)


def test_build_simple_plan_compiles() -> None:
    plan = Plan(
        plan_id="p-simple",
        steps=[_step("a"), _step("b", deps=["a"], task_type="long_writing")],
        primary_artifact="b",
    )
    builder = build_state_graph_from_plan(
        plan, dispatcher=_noop_dispatch, result_waiter=_noop_wait
    )
    nodes = set(builder.nodes.keys())
    # planner / step_a / step_b / finalize 全部在
    assert {"planner", "step_a", "step_b", "finalize"} <= nodes


def test_build_diamond_plan_compiles() -> None:
    plan = Plan(
        plan_id="p-diamond",
        steps=[
            _step("a"),
            _step("b", deps=["a"], task_type="long_writing"),
            _step("c", deps=["a"], agent="agent_3", task_type="image_download"),
            _step("d", deps=["b", "c"], agent="agent_4", task_type="video_compose"),
        ],
        primary_artifact="d",
    )
    builder = build_state_graph_from_plan(
        plan, dispatcher=_noop_dispatch, result_waiter=_noop_wait
    )
    nodes = set(builder.nodes.keys())
    assert {"step_a", "step_b", "step_c", "step_d"} <= nodes


def test_plan_with_hitl_gate_translates() -> None:
    plan = Plan(
        plan_id="p-hitl",
        steps=[
            _step("a"),
            _step(
                "b",
                deps=["a"],
                task_type="long_writing",
                hitl_gate=HITLGateSpec(type="version_select", timeout_seconds=300),
            ),
        ],
        primary_artifact="b",
    )
    sy = plan_to_skill_yaml(plan)
    assert sy["workflow"][1]["hitl_gate"]["type"] == "version_select"
    # build_state_graph 不抛
    build_state_graph_from_plan(
        plan, dispatcher=_noop_dispatch, result_waiter=_noop_wait
    )


def test_invalid_plan_missing_dep_fails_early() -> None:
    plan = Plan(
        plan_id="p-bad",
        steps=[_step("a", deps=["ghost"])],
    )
    with pytest.raises(PlanValidationError):
        build_state_graph_from_plan(
            plan, dispatcher=_noop_dispatch, result_waiter=_noop_wait
        )


def test_invalid_plan_cycle_detected_via_compile_to_dag() -> None:
    """Plan 自身的 validate_deps 不查环(深度有限);build_state_graph 内部
    会调 compile_to_dag,在那里被环检测捕获。"""
    plan = Plan(
        plan_id="p-cycle",
        steps=[
            _step("a", deps=["b"]),
            _step("b", deps=["a"]),
        ],
    )
    # validate_deps 不查环(只查未声明引用),plan.validate_deps() 通过
    plan.validate_deps()
    # 但 build_state_graph 内部 compile_to_dag 会抓
    with pytest.raises(DAGCompileError):
        build_state_graph_from_plan(
            plan, dispatcher=_noop_dispatch, result_waiter=_noop_wait
        )


def test_skill_yaml_compatible_with_compile_to_dag() -> None:
    """关键:dynamic_compiler 产出的 skill_yaml 应能被既有 compile_to_dag 通过。"""
    plan = Plan(
        plan_id="p-compat",
        steps=[
            _step("a"),
            _step("b", deps=["a"], task_type="long_writing"),
            _step("c", deps=["a"], agent="agent_3", task_type="image_download"),
        ],
        primary_artifact="b",
    )
    sy = plan_to_skill_yaml(plan)
    dag = compile_to_dag(sy)
    assert {s.step_id for s in dag.steps} == {"a", "b", "c"}
    assert dag.primary_artifact == "b"
    # 拓扑分层:a 第 0 层,b/c 第 1 层
    assert dag.levels[0] == ["a"]
    assert set(dag.levels[1]) == {"b", "c"}
