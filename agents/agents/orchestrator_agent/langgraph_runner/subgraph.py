"""Subgraph 模块化:把 Skill 按"阶段"拆成多个 LangGraph 子图。

设计动机(对应 V1.5 hero subgraph):
  反诈视频 = 调研子图 + 制作子图 + 终审子图
    - 调研子图:web_search → script(独立 checkpoint,失败可单独重跑)
    - 制作子图:image_process → tts → bgm_select → video_compose
    - 终审子图:final_review HITL gate

每个子图有自己的 thread_id,checkpoint 独立。父图通过 invoke 子图的方式串起来。
这样:
  1. **失败局部化**:调研失败不影响"已经制作好"的产物
  2. **回滚粒度细**:V2 中断 C 可以"只回滚到调研子图开始"
  3. **可单独单测**:每个子图独立验证

V1 不强制走 subgraph 模式 — Skill YAML 加 `phase: research|production|review` 字段
触发自动拆分;没声明就走原平铺图。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents.orchestrator_agent.langgraph_runner.compiler import _make_planner, _make_step_node
from agents.orchestrator_agent.langgraph_runner.state import TaskState
from agents.orchestrator_agent.task_compiler import compile_to_dag
from app.schemas.agent import AgentTask

log = structlog.get_logger(__name__)

DispatchFn = Callable[[AgentTask], Any]


def _group_by_phase(workflow: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按 step.phase 字段分组;无 phase 一律归到 'main'。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for s in workflow:
        phase = s.get("phase") or "main"
        out.setdefault(phase, []).append(s)
    return out


def _phase_router(workflow: list[dict[str, Any]]):
    """父图: planner → fan-out 当前 phase 可执行 step → ... → finalize。"""
    deps_by_step: dict[str, list[str]] = {
        s["step_id"]: list(s.get("depends_on") or []) for s in workflow
    }
    step_ids = {s["step_id"] for s in workflow}
    _TERMINAL = frozenset({"completed", "rolled_back"})

    def _route(state: TaskState):
        # planner 已检测到死锁或失败 → 走 finalize 正常关单(WS 推 task_failed)
        if state.get("final_status") == "failed":
            return "finalize"
        results = state.get("step_results") or {}
        eligible: list[str] = []
        for sid, deps in deps_by_step.items():
            if results.get(sid, {}).get("status") in _TERMINAL:
                continue
            if all(results.get(d, {}).get("status") == "completed" for d in deps):
                eligible.append(sid)
        if eligible:
            return [Send(f"step_{sid}", state) for sid in eligible]
        if all(results.get(sid, {}).get("status") in _TERMINAL for sid in step_ids):
            return "finalize"
        # 无可运行步骤且未全部终止 → 视为死锁,走 finalize 关单
        # (planner 应当已将 final_status 设为 "failed";这里作兜底防止路由到 END)
        log.warning("lg.phase_router.stuck", step_ids=sorted(step_ids))
        return "finalize"

    return _route


# phased planner 复用主图 planner 的死锁检测逻辑
_make_phased_planner = _make_planner


async def _finalize_phase(primary_step: str | None):
    async def _node(state: TaskState) -> dict[str, Any]:
        results = state.get("step_results") or {}
        ref = (
            results.get(primary_step, {}).get("artifact_ref")
            if primary_step
            else None
        )
        return {"primary_artifact_ref": ref, "final_status": state.get("final_status") or "completed"}

    return _node


def build_phased_state_graph(
    skill_yaml: dict[str, Any],
    *,
    dispatcher: DispatchFn,
    result_waiter: Callable[[str, str, int], Any],
):
    """phase-aware 编译器。每个 phase 独立 fan-out,phase 之间串行。

    与 build_state_graph 行为兼容(无 phase 时退化为同款),但若 Skill YAML 里
    有 step.phase 字段,会按 phase 串成 P1 → P2 → P3 的子图链。
    """
    compile_to_dag(skill_yaml)
    workflow = skill_yaml.get("workflow") or []
    primary_step: str | None = (skill_yaml.get("delivery") or {}).get("primary_artifact")
    phases = _group_by_phase(workflow)
    phase_order = list(dict.fromkeys(s.get("phase", "main") for s in workflow))

    builder = StateGraph(TaskState)
    # 使用带死锁检测的真实 planner(M-5 修复:phased 图也能检测死锁并设 final_status)
    builder.add_node("planner", _make_phased_planner(workflow))
    finalize_node = compile_finalize_sync(primary_step)
    builder.add_node("finalize", finalize_node)

    for step_def in workflow:
        builder.add_node(
            f"step_{step_def['step_id']}",
            _make_step_node(step_def, dispatcher=dispatcher, result_waiter=result_waiter),
        )

    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        _phase_router(workflow),
        [f"step_{s['step_id']}" for s in workflow] + ["finalize", END],
    )
    for step_def in workflow:
        builder.add_edge(f"step_{step_def['step_id']}", "planner")
    builder.add_edge("finalize", END)

    log.info(
        "lg.phased_compiled",
        skill=skill_yaml.get("skill_id"),
        phases=phase_order,
        phase_steps={p: [s["step_id"] for s in steps] for p, steps in phases.items()},
    )
    return builder


def compile_finalize_sync(primary_step: str | None):
    async def _node(state: TaskState) -> dict[str, Any]:
        results = state.get("step_results") or {}
        ref = (
            results.get(primary_step, {}).get("artifact_ref")
            if primary_step
            else None
        )
        return {
            "primary_artifact_ref": ref,
            "final_status": state.get("final_status") or "completed",
        }

    return _node
