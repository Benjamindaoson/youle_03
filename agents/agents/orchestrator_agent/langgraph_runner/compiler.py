"""Skill YAML → LangGraph StateGraph 编译器。

每个 Skill workflow step 对应一个 LangGraph 节点,它做的事是:
  1. 从 state.collected_fields 渲染 prompt_template
  2. 通过 Redis Streams 派发 AgentTask 到对应 Agent worker
  3. 阻塞等待 agent_results:<task_id> stream 上该 step 的回执
  4. 写回 state.step_results[step_id]
  5. 若 step 配 hitl_gate → 调 interrupt() 暂停,等用户决议

并行 fan-out 策略:
  - 用 conditional_edges 从入口节点 yield Send("step_X", state) 列表
    给所有 deps 已满足的 step,LangGraph 自己跑同层并行
  - 每个 step 完成后再 dispatch 下一层

铁律 13 守住:Agent 派发依然走 Redis Streams,LangGraph 不直接调 Agent 函数。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agents.orchestrator_agent.langgraph_runner.compiler_md_knowledge import (
    resolve_md_knowledge_prefix,
)
from agents.orchestrator_agent.langgraph_runner.compiler_step_node import make_step_node
from agents.orchestrator_agent.langgraph_runner.state import TaskState
from agents.orchestrator_agent.task_compiler import compile_to_dag
from app.schemas.agent import AgentTask

_make_step_node = make_step_node  # 兼容 subgraph 等旧 import

log = structlog.get_logger(__name__)

DispatchFn = Callable[[AgentTask], Any]  # async

# 节点级重试策略(Tier-1 韧性,铁律 #12):网络/瞬态异常自动重试
STEP_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    backoff_factor=2.0,
    jitter=True,
)


# ─────────────────────────────────────────────────────────────────
# Send 路由(动态 fan-out)
# ─────────────────────────────────────────────────────────────────
def _make_router(workflow: list[dict[str, Any]], primary_step: str | None = None):
    """从入口 "plan" 节点路由出去，把所有 deps 满足且未完成的 step 用 Send 派出。"""

    deps_by_step: dict[str, list[str]] = {
        s["step_id"]: list(s.get("depends_on") or []) for s in workflow
    }

    def _eligible(state: TaskState) -> list[str]:
        results = state.get("step_results") or {}
        out: list[str] = []
        for sid, deps in deps_by_step.items():
            if sid in results and results[sid].get("status") in ("completed", "rolled_back"):
                continue
            if sid in results and results[sid].get("status") == "running":
                continue  # 防止 fan-in 时重复派
            if all(
                d in results and results[d].get("status") == "completed" for d in deps
            ):
                out.append(sid)
        return out

    def _route(state: TaskState):
        # 任务已失败 → 走 finalize 正常关单(WS 推 task_failed、DB 关单)
        if state.get("final_status") == "failed":
            return "finalize"
        # 还有待执行 step，继续 fan-out
        eligible = _eligible(state)
        if eligible:
            return [Send(f"step_{sid}", state) for sid in eligible]
        # 所有 step 完成，终结
        results = state.get("step_results") or {}
        if all(
            results.get(s["step_id"], {}).get("status") in ("completed", "rolled_back")
            for s in workflow
        ):
            return "finalize"
        # 兜底:planner 应在前一轮已写 final_status=failed,此处不应到达
        return "handle_deadlock"

    return _route


# ─────────────────────────────────────────────────────────────────
# finalize / planner 节点
# ─────────────────────────────────────────────────────────────────
def _make_planner(workflow: list[dict[str, Any]]):
    """planner:deadlock 检测 + 幂等守卫。fan-out 靠 router 的条件边实现。"""
    deps_by_step: dict[str, list[str]] = {
        s["step_id"]: list(s.get("depends_on") or []) for s in workflow
    }
    step_ids: set[str] = {s["step_id"] for s in workflow}
    _TERMINAL = frozenset({"completed", "rolled_back"})

    async def _planner(state: TaskState) -> dict[str, Any]:
        # 幂等:已经失败,不重复改写
        if state.get("final_status") == "failed":
            return {}

        results = state.get("step_results") or {}

        # 有 eligible step → 正常交给 router fan-out
        for sid, deps in deps_by_step.items():
            if results.get(sid, {}).get("status") in _TERMINAL:
                continue
            if all(results.get(d, {}).get("status") == "completed" for d in deps):
                return {}  # 至少一个 eligible

        # 所有 step 终态 → 让 router 走 finalize
        if all(results.get(sid, {}).get("status") in _TERMINAL for sid in step_ids):
            return {}

        # 死锁检测:步骤不是终态也不是 failed(可重试),但有 dep 是 rolled_back
        blocked = [
            sid for sid, deps in deps_by_step.items()
            if results.get(sid, {}).get("status") not in _TERMINAL
            and results.get(sid, {}).get("status") != "failed"
            and any(results.get(d, {}).get("status") == "rolled_back" for d in deps)
        ]
        if blocked:
            log.error(
                "lg.planner_deadlock",
                task_id=state.get("task_id"),
                blocked=blocked,
            )
            return {
                "final_status": "failed",
                "failure_reason": f"deadlock: {', '.join(sorted(blocked))}",
            }

        return {}

    return _planner


def _make_deadlock_handler():
    """死锁兜底节点:既没有 eligible steps 也没有全部完成时记录错误并终止。"""

    async def _deadlock(state: TaskState) -> dict[str, Any]:
        results = state.get("step_results") or {}
        completed = [k for k, v in results.items() if v.get("status") == "completed"]
        stuck = [k for k, v in results.items() if v.get("status") not in ("completed", "rolled_back")]
        log.error(
            "lg.router_deadlock",
            task_id=state.get("task_id"),
            completed=completed,
            stuck=stuck,
        )
        return {
            "final_status": "failed",
            "failure_reason": f"router_deadlock: stuck steps {stuck}",
        }

    return _deadlock


def _make_finalize(primary_step: str | None):
    async def _finalize(state: TaskState) -> dict[str, Any]:
        results = state.get("step_results") or {}
        primary_ref = None
        if primary_step and primary_step in results:
            primary_ref = results[primary_step].get("artifact_ref")
        return {
            "final_status": state.get("final_status") or "completed",
            "primary_artifact_ref": primary_ref,
        }

    return _finalize


# ─────────────────────────────────────────────────────────────────
# 顶层:build_state_graph
# ─────────────────────────────────────────────────────────────────
def build_state_graph(
    skill_yaml: dict[str, Any],
    *,
    dispatcher: DispatchFn,
    result_waiter: Callable[[str, str, int], Any],
):
    """编译 Skill YAML 为 LangGraph 图(未编译,等 runner 加 checkpointer)。"""
    # 复用现有 DAG 校验(环检测 / 缺失 dep / 重复 step_id)
    compile_to_dag(skill_yaml)

    workflow: list[dict[str, Any]] = skill_yaml.get("workflow") or []
    primary_step: str | None = (skill_yaml.get("delivery") or {}).get("primary_artifact")

    fh_raw = skill_yaml.get("failure_handling")
    failure_handling = fh_raw if isinstance(fh_raw, dict) else {}

    md_knowledge_prefix = resolve_md_knowledge_prefix(skill_yaml)

    builder = StateGraph(TaskState)
    builder.add_node("planner", _make_planner(workflow))
    builder.add_node("finalize", _make_finalize(primary_step))
    builder.add_node("handle_deadlock", _make_deadlock_handler())

    for step_def in workflow:
        builder.add_node(
            f"step_{step_def['step_id']}",
            _make_step_node(
                step_def,
                dispatcher=dispatcher,
                result_waiter=result_waiter,
                failure_handling=failure_handling,
                md_knowledge_prefix=md_knowledge_prefix,
            ),
            retry_policy=STEP_RETRY_POLICY,
        )

    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        _make_router(workflow, primary_step),
        [f"step_{s['step_id']}" for s in workflow] + ["finalize", "handle_deadlock", END],
    )
    for step_def in workflow:
        builder.add_edge(f"step_{step_def['step_id']}", "planner")

    builder.add_edge("finalize", END)
    builder.add_edge("handle_deadlock", END)
    return builder
