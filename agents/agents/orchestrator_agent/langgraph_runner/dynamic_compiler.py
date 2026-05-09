"""Plan → LangGraph StateGraph(ADR-019)。

# 设计哲学
**不引入新引擎,只新增"input source"**。

YAML 路径:
    skill_yaml(dict from yaml.safe_load) → build_state_graph() → StateGraph

Dynamic 路径:
    user_request → Planner → Plan → Plan.to_skill_yaml() → build_state_graph() → StateGraph
                                    ↑
                                这里(本文件)

也就是说,**dynamic_compiler 不重写 compiler.py 的任何逻辑**,只是把 Plan
翻成 skill_yaml dict 然后委托给 `build_state_graph`。这样:

1. 节点工厂、HITL、failure_handling、router、finalize 全部复用,零分叉
2. 任何对 compiler 的优化(性能/可观测性)dynamic 路径自动受益
3. 测试矩阵小:只验证"Plan → skill_yaml 翻译正确",compiler 的语义已被
   既有测试覆盖

# 与 ADR-017(LangGraph 唯一内核)的关系
不冲突 — 内核仍是 LangGraph,本文件只增加一个进入内核的"前置入口"。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from agents.orchestrator_agent.langgraph_runner.compiler import (
    DispatchFn,
    build_state_graph,
)
from agents.orchestrator_agent.planner.plan_schema import Plan

log = structlog.get_logger(__name__)


def build_state_graph_from_plan(
    plan: Plan,
    *,
    dispatcher: DispatchFn,
    result_waiter: Callable[[str, str, int], Any],
):
    """编译 Plan 为 LangGraph StateGraph(未编译,等 runner 加 checkpointer)。

    Args:
        plan: 已通过 schema 校验的 Plan。
        dispatcher: 与 YAML 路径同一份 dispatcher(Redis Streams 派单)。
        result_waiter: 与 YAML 路径同一份 result_waiter。

    Returns:
        与 `compiler.build_state_graph` 同 shape 的 StateGraphBuilder。

    Raises:
        PlanValidationError / DAGCompileError:plan 内部不一致或 DAG 非法。
    """
    plan.validate_deps()
    skill_yaml = plan.to_skill_yaml()

    log.info(
        "dynamic_compiler.build",
        plan_id=plan.plan_id,
        steps=len(plan.steps),
        primary=plan.primary_artifact,
        source=plan.source,
        cognitive_model=plan.cognitive_model,
    )

    return build_state_graph(
        skill_yaml,
        dispatcher=dispatcher,
        result_waiter=result_waiter,
    )


def plan_to_skill_yaml(plan: Plan) -> dict[str, Any]:
    """便利函数 — 测试 / 调试时单独看翻译产物。

    生产链路调用方应直接用 `build_state_graph_from_plan`。
    """
    plan.validate_deps()
    return plan.to_skill_yaml()
