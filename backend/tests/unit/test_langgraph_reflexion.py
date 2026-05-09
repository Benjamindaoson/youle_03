"""Reflexion graph(替代飞轮 reflexion runner 单步)单测。

只测 graph 结构 + 控制流 — 不测真 LLM(那是 flywheel/reflexion/runner.py 的集成范围)。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agents.orchestrator_agent.langgraph_runner.reflexion_graph import build_reflexion_graph


@pytest.mark.asyncio
async def test_reflexion_graph_persists_when_llm_ok() -> None:
    fake_llm_resp = MagicMock()
    fake_llm_resp.content = (
        '{"root_cause":"prompt 缺约束","section_to_improve":"intro",'
        '"current_text":"old","proposed_changes":"加 bullet","expected_improvement":"清晰度↑"}'
    )

    fake_session = MagicMock()
    fake_session.add = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "agents.orchestrator_agent.langgraph_runner.reflexion_graph.complete",
        AsyncMock(return_value=fake_llm_resp),
    ), patch(
        "agents.orchestrator_agent.langgraph_runner.reflexion_graph.SessionLocal",
        return_value=fake_session,
    ):
        graph = build_reflexion_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "t1"}}
        out = await graph.ainvoke(
            {
                "task_id": str(uuid4()),
                "prompt_name": "agent_1.long_writing",
                "trace_excerpt": "step b failed",
                "failure_reason": "tts timeout",
                "messages": [],
            },
            config,
        )
    assert out.get("root_cause") == "prompt 缺约束"
    assert out.get("candidate_id")  # 落库成功 → 有 id
    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_reflexion_graph_skips_persist_when_llm_fails() -> None:
    """LLM 抛 → 节点返回 error → graph 直接 END,不写 DB。

    重要:checkpoint 保留中间状态,V2 排查后可 invoke(None) 续跑。
    """
    fake_session = MagicMock()
    fake_session.add = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "agents.orchestrator_agent.langgraph_runner.reflexion_graph.complete",
        AsyncMock(side_effect=RuntimeError("rate limit")),
    ), patch(
        "agents.orchestrator_agent.langgraph_runner.reflexion_graph.SessionLocal",
        return_value=fake_session,
    ):
        graph = build_reflexion_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "t2"}}
        out = await graph.ainvoke(
            {
                "task_id": str(uuid4()),
                "prompt_name": "x",
                "trace_excerpt": "",
                "failure_reason": "boom",
                "messages": [],
            },
            config,
        )
    assert out.get("error", "").startswith("llm_failed")
    fake_session.add.assert_not_called()  # 没落库
