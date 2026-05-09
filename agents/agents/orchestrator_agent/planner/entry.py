"""Planner 集成入口 — `plan_and_compile()`(ADR-019)。

# 角色
这一文件是**未来**整合到 `backend/app/api/messages.py` 的桥梁。S1 阶段:

- production 路径(Skill 命中走 YAML)**完全不调用本文件**
- 单测和灰度场景从这里进入,验证 Planner → dynamic_compiler 端到端可工作
- S2 集成时:在 messages.py 中,Skill 不命中(或匹配置信度 < 阈值)时调
  `plan_and_compile()`,拿回 (skill_yaml, plan_meta),然后走原有 task 创建流程

# 这样设计的理由
1. **production 零风险**:本文件不被 messages.py / runner_factory 引用,
   只能被显式调用。
2. **dispatcher / result_waiter 的注入**保持与 YAML 路径一致 — 调用方负责
   传入,本函数不耦合具体派单实现。
3. **flag 双控**:`is_dynamic_plan_enabled()` 让上游能集中判断,避免遍地
   `os.getenv("ENABLE_DYNAMIC_PLAN")`。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import structlog

from agents.orchestrator_agent.langgraph_runner.dynamic_compiler import (
    build_state_graph_from_plan,
)
from agents.orchestrator_agent.planner.plan_schema import Plan
from agents.orchestrator_agent.planner.planner_agent import (
    PlannerError,
    make_plan,
)

log = structlog.get_logger(__name__)


def is_dynamic_plan_enabled() -> bool:
    """ENABLE_DYNAMIC_PLAN=true 时启用动态规划路径(默认 false,不影响生产)。"""
    return os.getenv("ENABLE_DYNAMIC_PLAN", "false").lower() in {"1", "true", "yes"}


async def plan_and_compile(
    *,
    user_request: str,
    user_id: str,
    collected_fields: dict[str, Any] | None = None,
    available_skills_index: list[dict[str, Any]] | None = None,
    available_mcp_tools: list[dict[str, str]] | None = None,
    skill_registry: Any | None = None,
    dispatcher: Callable[..., Any],
    result_waiter: Callable[[str, str, int], Any],
) -> tuple[Plan, dict[str, Any], Any]:
    """端到端:用户请求 → Plan → skill_yaml dict → StateGraphBuilder。

    Returns:
        (plan, skill_yaml_dict, state_graph_builder)
        - plan:Plan 对象,可直接落库(task.parameters.dynamic_plan)
        - skill_yaml_dict:Plan.to_skill_yaml() 产物;调用方应放进
          TaskState.skill_yaml 字段(state.py 已支持任意 dict)
        - state_graph_builder:未 compile 的 builder;调用方挂上 checkpointer
          后再 builder.compile(checkpointer=...)

    Args(ADR-022):
        skill_registry:覆盖默认 SkillRegistry(测试 / 自定义目录);None 走默认。

    Raises:
        PlannerError:Planner 多次输出无效 plan,上游应回退到澄清流程。
    """
    plan: Plan = await make_plan(
        user_request=user_request,
        user_id=user_id,
        collected_fields=collected_fields,
        available_skills_index=available_skills_index,
        available_mcp_tools=available_mcp_tools,
        skill_registry=skill_registry,
    )

    log.info(
        "planner.plan_and_compile.ok",
        plan_id=plan.plan_id,
        steps=len(plan.steps),
        user_id=user_id,
    )

    skill_yaml_dict = plan.to_skill_yaml()
    builder = build_state_graph_from_plan(
        plan,
        dispatcher=dispatcher,
        result_waiter=result_waiter,
    )
    return plan, skill_yaml_dict, builder


__all__ = ["is_dynamic_plan_enabled", "plan_and_compile", "PlannerError"]
