"""LangGraph runtime:用 InMemorySaver 完整跑一个 mini graph(无 DB / 无 Redis)。

模拟 dispatcher / result_waiter,验证:
  1. 简单线性 a→b 跑完,产物落 step_results
  2. interrupt() 暂停 + Command(resume=...) 恢复
  3. time-travel:aupdate_state 改 collected_fields + 清下游 → 重跑
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph
from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.schemas.agent import AgentResult, ArtifactRef


def _mk_skill(workflow, *, primary=None):
    yml = {"skill_id": "test", "version": "1.0", "workflow": workflow}
    if primary:
        yml["delivery"] = {"primary_artifact": primary}
    return yml


class _FakeQueue:
    """记录派发 + 提供回执的简易 fixture。"""

    def __init__(self):
        self.dispatched: list[Any] = []
        self.results: dict[str, AgentResult] = {}

    async def dispatch(self, agent_task):
        self.dispatched.append(agent_task)

    def queue_result(self, *, task_id, step_id, status="completed", artifact_ref=None):
        self.results[step_id] = AgentResult(
            task_id=task_id,
            step_id=step_id,
            status=status,
            output=(
                ArtifactRef(
                    artifact_id=uuid4(),
                    type="text",
                    reference=artifact_ref or f"oss://test/{step_id}.txt",
                    extra_metadata={},
                )
                if artifact_ref or status == "completed"
                else None
            ),
            duration_ms=10,
        )

    async def wait(self, task_id, step_id, timeout):
        # 给点时间让 dispatch 先记录 — 实际 result 是预先 queue 的
        for _ in range(20):
            if step_id in self.results:
                return self.results[step_id]
            await asyncio.sleep(0.01)
        return None


def _initial_state(skill_yaml, **fields):
    return make_initial_state(
        task_id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        skill_yaml=skill_yaml,
        collected_fields=fields,
    )


@pytest.mark.asyncio
async def test_linear_graph_runs_to_completion() -> None:
    skill = _mk_skill(
        [
            {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
            {
                "step_id": "b",
                "agent": "agent_1",
                "task_type": "long_writing",
                "depends_on": ["a"],
            },
        ],
        primary="b",
    )
    q = _FakeQueue()
    builder = build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    saver = InMemorySaver()
    graph = builder.compile(checkpointer=saver)

    state = _initial_state(skill, topic="demo")
    q.queue_result(task_id=state["task_id"], step_id="a", artifact_ref="oss://a.txt")
    q.queue_result(task_id=state["task_id"], step_id="b", artifact_ref="oss://b.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)
    assert final["step_results"]["a"]["status"] == "completed"
    assert final["step_results"]["b"]["status"] == "completed"
    assert final["primary_artifact_ref"] == "oss://b.txt"
    # dispatch 实际发生 2 次
    assert len(q.dispatched) == 2


@pytest.mark.asyncio
async def test_interrupt_pauses_and_resumes() -> None:
    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                "task_type": "long_writing",
                "hitl_gate": {"gate_type": "quality_review"},
            },
            {
                "step_id": "render",
                "agent": "agent_3",
                "task_type": "image_download",
                "depends_on": ["draft"],
            },
        ]
    )
    q = _FakeQueue()
    builder = build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill)
    q.queue_result(task_id=state["task_id"], step_id="draft", artifact_ref="oss://d.txt")
    q.queue_result(task_id=state["task_id"], step_id="render", artifact_ref="oss://r.png")
    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}

    # 第一跑:draft 完成 → interrupt
    await graph.ainvoke(state, config)
    snap = await graph.aget_state(config)
    assert snap.next  # paused
    interrupts = []
    for t in snap.tasks or []:
        interrupts.extend(getattr(t, "interrupts", []) or [])
    assert any(
        (getattr(i, "value", {}) or {}).get("kind") == "hitl_gate"
        for i in interrupts
    )
    # render 还没跑
    assert "render" not in (snap.values or {}).get("step_results", {})

    # 用户决议 → resume
    await graph.ainvoke(Command(resume={"resolution": "approved"}), config)
    snap = await graph.aget_state(config)
    assert (snap.values or {})["step_results"]["render"]["status"] == "completed"


@pytest.mark.asyncio
async def test_interrupt_rejected_marks_failed() -> None:
    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                "task_type": "long_writing",
                "hitl_gate": {"gate_type": "final_approval"},
            },
        ]
    )
    q = _FakeQueue()
    builder = build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())
    state = _initial_state(skill)
    q.queue_result(task_id=state["task_id"], step_id="draft", artifact_ref="oss://d.txt")
    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    await graph.ainvoke(state, config)
    await graph.ainvoke(
        Command(resume={"resolution": "rejected", "feedback": "不行"}), config
    )
    snap = await graph.aget_state(config)
    assert (snap.values or {})["final_status"] == "failed"


@pytest.mark.asyncio
async def test_time_travel_rollback_reruns_downstream() -> None:
    """V2 中断 C/D 的 LangGraph 价值证明:可以回滚到 a 完成后重跑 b。"""
    skill = _mk_skill(
        [
            {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
            {
                "step_id": "b",
                "agent": "agent_1",
                "task_type": "long_writing",
                "depends_on": ["a"],
            },
        ]
    )
    q = _FakeQueue()
    builder = build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())
    state = _initial_state(skill, topic="demo")
    q.queue_result(task_id=state["task_id"], step_id="a", artifact_ref="oss://a-v1.txt")
    q.queue_result(task_id=state["task_id"], step_id="b", artifact_ref="oss://b-v1.txt")
    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)
    assert final["step_results"]["b"]["artifact_ref"] == "oss://b-v1.txt"

    # 找回滚点 — history 是 reverse-chronological,跳过 b 已完成的 snapshot,
    # 找到第一个 b 尚未完成的(刚好是 a 完成、b 待跑的状态)
    target_checkpoint_id = None
    async for snap in graph.aget_state_history(config):
        results = (snap.values or {}).get("step_results") or {}
        b_done = (
            "b" in results and results["b"].get("status") == "completed"
        )
        if not b_done:
            target_checkpoint_id = snap.config["configurable"].get("checkpoint_id")
            break
    assert target_checkpoint_id

    anchor = {
        "configurable": {
            "thread_id": f"task:{state['task_id']}",
            "checkpoint_ns": "",
            "checkpoint_id": target_checkpoint_id,
        }
    }
    snap = await graph.aget_state(anchor)
    new_results = dict((snap.values or {}).get("step_results") or {})
    new_results.pop("b", None)  # 清下游
    await graph.aupdate_state(
        anchor,
        {
            "step_results": new_results,
            "collected_fields": {**(snap.values or {}).get("collected_fields", {}), "_user_instruction": "改一下"},
            "rollback_count": 1,
            "final_status": None,
        },
    )

    # 重新派发 b 的回执(模拟 v2 重跑)
    q.queue_result(task_id=state["task_id"], step_id="b", artifact_ref="oss://b-v2.txt")
    final2 = await graph.ainvoke(None, {"configurable": {"thread_id": f"task:{state['task_id']}"}})
    assert final2["step_results"]["b"]["artifact_ref"] == "oss://b-v2.txt"
    assert final2["rollback_count"] >= 1
