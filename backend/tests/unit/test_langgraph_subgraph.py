"""Subgraph(phase-aware)编译 + 跑通单测。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
from agents.orchestrator_agent.langgraph_runner.subgraph import build_phased_state_graph
from langgraph.checkpoint.memory import InMemorySaver

from app.schemas.agent import AgentResult, ArtifactRef


class _FakeQ:
    def __init__(self):
        self.results = {}
        self.dispatch_order: list[str] = []

    async def dispatch(self, t):
        self.dispatch_order.append(t.step_id)

    def queue(self, *, task_id, sid, ref="oss://x.txt"):
        self.results[sid] = AgentResult(
            task_id=task_id,
            step_id=sid,
            status="completed",
            output=ArtifactRef(artifact_id=uuid4(), type="text", reference=ref, extra_metadata={}),
            duration_ms=10,
        )

    async def wait(self, t, s, to):
        for _ in range(20):
            if s in self.results:
                return self.results[s]
            await asyncio.sleep(0.01)


def _hero_skill():
    return {
        "skill_id": "short_video",
        "version": "1.0",
        "delivery": {"primary_artifact": "compose"},
        "workflow": [
            # 调研 phase
            {"step_id": "search", "agent": "agent_1", "task_type": "web_search",
             "phase": "research"},
            {"step_id": "script", "agent": "agent_1", "task_type": "long_writing",
             "phase": "research", "depends_on": ["search"]},
            # 制作 phase(image / tts / bgm 可并行;compose 收口)
            {"step_id": "image", "agent": "agent_3", "task_type": "image_download",
             "phase": "production", "depends_on": ["script"]},
            {"step_id": "tts", "agent": "agent_4", "task_type": "tts_generate",
             "phase": "production", "depends_on": ["script"]},
            {"step_id": "bgm", "agent": "agent_4", "task_type": "bgm_select",
             "phase": "production", "depends_on": ["script"]},
            {"step_id": "compose", "agent": "agent_4", "task_type": "video_compose",
             "phase": "production", "depends_on": ["image", "tts", "bgm"]},
            # 终审 phase(HITL)
            {"step_id": "review", "agent": "agent_4", "task_type": "video_describe",
             "phase": "review", "depends_on": ["compose"],
             "hitl_gate": {"gate_type": "final_approval"}},
        ],
    }


@pytest.mark.asyncio
async def test_phased_hero_runs_with_parallel_production() -> None:
    """短视频 hero phased 编译 + 跑通,且 image/tts/bgm 在同 phase 内并行。"""
    skill = _hero_skill()
    q = _FakeQ()
    builder = build_phased_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = make_initial_state(
        task_id=uuid4(), user_id=uuid4(), conversation_id=uuid4(),
        skill_id=None, skill_version="1.0",
        skill_yaml=skill, collected_fields={},
    )
    for sid, ref in [
        ("search", "oss://research.json"),
        ("script", "oss://script.txt"),
        ("image", "oss://images/"),
        ("tts", "oss://voice.mp3"),
        ("bgm", "oss://bgm.mp3"),
        ("compose", "oss://final.mp4"),
        ("review", "oss://review.json"),
    ]:
        q.queue(task_id=state["task_id"], sid=sid, ref=ref)
    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}

    # 第 1 跑:跑到 review HITL → 暂停
    await graph.ainvoke(state, config)
    snap = await graph.aget_state(config)
    assert snap.next, "应当被 HITL gate 暂停"
    sr = (snap.values or {}).get("step_results", {})
    # 制作 phase 全跑完,review 待用户决议
    assert all(sr[s]["status"] == "completed" for s in ("search", "script", "image", "tts", "bgm", "compose"))
    assert "review" not in sr or sr["review"].get("status") != "completed"
    # image / tts / bgm 应在 script 之后被并行 dispatch — 顺序无关,但都在 compose 之前
    order = q.dispatch_order
    assert order.index("script") < order.index("image")
    assert order.index("script") < order.index("tts")
    assert order.index("script") < order.index("bgm")
    assert order.index("image") < order.index("compose")
    assert order.index("tts") < order.index("compose")
    assert order.index("bgm") < order.index("compose")


@pytest.mark.asyncio
async def test_phased_skill_without_phase_field_works() -> None:
    """无 phase 字段时退化为平铺图(向后兼容)。"""
    skill = {
        "skill_id": "x", "version": "1",
        "workflow": [
            {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
            {"step_id": "b", "agent": "agent_1", "task_type": "long_writing", "depends_on": ["a"]},
        ],
    }
    q = _FakeQ()
    builder = build_phased_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())
    state = make_initial_state(
        task_id=uuid4(), user_id=uuid4(), conversation_id=uuid4(),
        skill_id=None, skill_version="1", skill_yaml=skill, collected_fields={},
    )
    q.queue(task_id=state["task_id"], sid="a")
    q.queue(task_id=state["task_id"], sid="b")
    final = await graph.ainvoke(state, {"configurable": {"thread_id": f"task:{state['task_id']}"}})
    assert final["step_results"]["b"]["status"] == "completed"
