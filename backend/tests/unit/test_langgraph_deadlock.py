"""LangGraph 死锁检测单测(对齐 PR #3 修复)。

修复语义:
- planner 节点检测到 "没有任何 step 可继续 + 还有 step 未到终态" 时,
  写 final_status='failed' + failure_reason='deadlock: ...'
- router 命中 final_status='failed' 改走 'finalize'(而非裸 END),
  让 finalize 节点正常关单(WS 推 task_failed、DB 关单)。

回归点:
- 正常路径不变:eligible 有 → fan-out;全终态 → finalize
- 死锁场景:有 step failed 且下游 depends_on 它 → planner 标 failed
- 幂等:state 已是 failed → planner 不重复改写
- subgraph 模块的 phased planner / router 同语义

实现细节见:
- `agents/agents/orchestrator_agent/langgraph_runner/compiler.py`: _make_planner / _make_router
- `agents/agents/orchestrator_agent/langgraph_runner/subgraph.py`:  _make_phased_planner / _phase_router
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.orchestrator_agent.langgraph_runner.compiler import _make_planner, _make_router
from agents.orchestrator_agent.langgraph_runner.subgraph import (
    _make_phased_planner,
    _phase_router,
)


def _wf(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """简单 helper 让测试用例更紧凑。"""
    return steps


def _run(coro: Any) -> Any:
    """跑 async planner 的同步 helper。

    用 asyncio.run 而不是 get_event_loop().run_until_complete:后者在
    pytest-asyncio AUTO mode 下与其他 async 测试共享 loop 时会污染状态
    (loop closed / loop reused),全套件跑时偶发 fail。asyncio.run 每次
    新建独立 loop,隔离干净。
    """
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────
# compiler._make_planner — 死锁检测
# ─────────────────────────────────────────────────────────────────
def test_planner_detects_deadlock_when_dep_rolled_back() -> None:
    """A 被 rolled_back(终态但非 completed)→ B depends_on=A → 永远等不到 → deadlock。

    注:planner 的 eligible 判据是 "deps 全 completed",所以 rolled_back 是真死锁。
    `failed` 状态不算终态(允许重试),因此用 rolled_back 才能稳定触发。
    """
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y", "depends_on": ["A"]},
        ]
    )
    planner = _make_planner(workflow)

    state: dict[str, Any] = {
        "task_id": "t-1",
        "step_results": {"A": {"status": "rolled_back"}},
    }
    out = _run(planner(state))

    assert out.get("final_status") == "failed"
    reason = out.get("failure_reason") or ""
    assert "deadlock" in reason
    assert "B" in reason  # blocked step 应在诊断里


def test_planner_does_not_flag_when_eligible_exists() -> None:
    """A 已 rolled_back 但 C 独立支路仍 eligible → 不应判死锁。"""
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y", "depends_on": ["A"]},
            {"step_id": "C", "agent": "agent_3", "task_type": "z"},  # 独立支路
        ]
    )
    planner = _make_planner(workflow)

    state: dict[str, Any] = {
        "task_id": "t-2",
        "step_results": {"A": {"status": "rolled_back"}},
    }
    out = _run(planner(state))

    assert out == {}  # C 仍 eligible,没死锁,planner 啥也不写


def test_planner_no_op_when_all_terminal() -> None:
    """所有 step 都 completed/rolled_back → 不该误判死锁(交给 router 走 finalize)。"""
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y", "depends_on": ["A"]},
        ]
    )
    planner = _make_planner(workflow)

    state: dict[str, Any] = {
        "task_id": "t-3",
        "step_results": {
            "A": {"status": "completed"},
            "B": {"status": "completed"},
        },
    }
    assert _run(planner(state)) == {}


def test_planner_idempotent_when_already_failed() -> None:
    """state 已是 failed → planner 直接返回 {} 不重复改写 reason。"""
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y", "depends_on": ["A"]},
        ]
    )
    planner = _make_planner(workflow)

    state: dict[str, Any] = {
        "task_id": "t-4",
        "final_status": "failed",
        "failure_reason": "external_cause",
        "step_results": {"A": {"status": "rolled_back"}},
    }
    out = _run(planner(state))
    assert out == {}


def test_planner_does_not_deadlock_when_failed_step_can_retry() -> None:
    """A 失败但 deps 为空 → 仍被视作可重试(eligible)→ 不应判死锁。

    这是个有意的设计:planner 不假设 failed step 一定不再恢复。重试 / 跳过的
    决定权交给上层(runner / Skill 重试策略)。
    """
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y", "depends_on": ["A"]},
        ]
    )
    planner = _make_planner(workflow)
    out = _run(
        planner({"task_id": "t-5", "step_results": {"A": {"status": "failed"}}})
    )
    assert out == {}  # A 仍可重试 → 没死锁


# ─────────────────────────────────────────────────────────────────
# compiler._make_router — failed 走 finalize 而非 END
# ─────────────────────────────────────────────────────────────────
def test_router_routes_failed_state_to_finalize() -> None:
    """final_status=failed → router 返回 'finalize'(不是裸 END)。"""
    workflow = _wf([{"step_id": "A", "agent": "agent_1", "task_type": "x"}])
    route = _make_router(workflow)
    decision = route({"final_status": "failed", "step_results": {}})
    assert decision == "finalize"


def test_router_returns_finalize_when_all_terminal() -> None:
    """全部 step 终态 → 走 finalize 关单。"""
    workflow = _wf([{"step_id": "A", "agent": "agent_1", "task_type": "x"}])
    route = _make_router(workflow)
    decision = route({"step_results": {"A": {"status": "completed"}}})
    assert decision == "finalize"


def test_router_returns_send_list_when_eligible() -> None:
    """有 eligible step → 返回 Send 列表(LangGraph fan-out)。"""
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x"},
            {"step_id": "B", "agent": "agent_2", "task_type": "y"},
        ]
    )
    route = _make_router(workflow)
    decision = route({"step_results": {}})
    # decision 是 list[Send],每个 Send 指向一个 step_X 节点
    assert isinstance(decision, list)
    targets = sorted(getattr(s, "node", "") for s in decision)
    assert targets == ["step_A", "step_B"]


# ─────────────────────────────────────────────────────────────────
# subgraph 模块同语义验证
# ─────────────────────────────────────────────────────────────────
def test_phased_planner_detects_deadlock() -> None:
    workflow = _wf(
        [
            {"step_id": "A", "agent": "agent_1", "task_type": "x", "phase": "research"},
            {
                "step_id": "B",
                "agent": "agent_2",
                "task_type": "y",
                "depends_on": ["A"],
                "phase": "production",
            },
        ]
    )
    planner = _make_phased_planner(workflow)
    out = _run(
        planner(
            {"task_id": "t-p1", "step_results": {"A": {"status": "rolled_back"}}}
        )
    )
    assert out.get("final_status") == "failed"
    assert "deadlock" in (out.get("failure_reason") or "")


def test_phase_router_routes_failed_to_finalize() -> None:
    workflow = _wf(
        [{"step_id": "A", "agent": "agent_1", "task_type": "x", "phase": "main"}]
    )
    route = _phase_router(workflow)
    assert route({"final_status": "failed", "step_results": {}}) == "finalize"
