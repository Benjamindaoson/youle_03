from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = ROOT / "agents"
BACKEND_ROOT = ROOT / "backend"
for path in (str(BACKEND_ROOT), str(AGENTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")
_load_env_file(AGENTS_ROOT / ".env")
os.environ["LITELLM_MOCK"] = "false"
os.environ["DEBUG"] = "true"
os.environ.setdefault("AGENT_HEARTBEAT_INTERVAL", "60")


@pytest.mark.asyncio
async def test_agent1_short_writing_via_langgraph_redis_live(monkeypatch):
    import agents._common.llm as llm
    import agents.text_agent.handlers.short_writing as short_writing
    from agents._common.consumer import AgentConsumer
    from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph
    from agents.orchestrator_agent.langgraph_runner.result_waiter import wait_for_step_result
    from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
    from app.services.dispatcher import dispatch_task

    importlib.reload(llm)
    importlib.reload(short_writing)

    captured: dict[str, str] = {}

    async def fake_put_text(*, key, content, content_type="text/plain"):
        captured["key"] = key
        captured["content"] = content
        captured["content_type"] = content_type
        return f"oss://live-test/{key}"

    monkeypatch.setattr(short_writing, "put_text", fake_put_text)

    consumer = AgentConsumer(
        agent_id="agent_1",
        handlers={"short_writing": short_writing.short_writing_handler},
        consumer_name=f"live-short-writing-{uuid4().hex}",
    )
    await consumer._r()
    consumer_task = asyncio.create_task(consumer.start())

    task_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    step_id = "short_writing_live"
    skill_yaml = {
        "skill_id": "live_agent1_short_writing",
        "version": "0.1",
        "workflow": [
            {
                "step_id": step_id,
                "agent": "agent_1",
                "task_type": "short_writing",
                "timeout": 180,
                "parameters": {"max_tokens": 80},
                "prompt_template": (
                    "给一家社区咖啡店写一条中文朋友圈短文案，"
                    "25字以内，温暖但不夸张。"
                ),
            }
        ],
        "delivery": {"primary_artifact": step_id},
    }

    try:
        graph = build_state_graph(
            skill_yaml,
            dispatcher=dispatch_task,
            result_waiter=wait_for_step_result,
        ).compile()
        initial_state = make_initial_state(
            task_id=task_id,
            user_id=user_id,
            conversation_id=conversation_id,
            skill_id=None,
            skill_version="0.1",
            skill_yaml=skill_yaml,
            collected_fields={},
        )

        final_state = await asyncio.wait_for(graph.ainvoke(initial_state), timeout=240)
    finally:
        consumer.stop()
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task

    step_result = final_state["step_results"][step_id]
    assert step_result["status"] == "completed"
    assert step_result["agent_id"] == "agent_1"
    assert step_result["task_type"] == "short_writing"
    assert step_result["artifact_type"] == "text"
    assert step_result["artifact_ref"].startswith("oss://live-test/artifacts/")
    assert step_result["model_used"]
    assert final_state["final_status"] == "completed"
    assert final_state["primary_artifact_ref"] == step_result["artifact_ref"]
    assert captured["content"].strip()
