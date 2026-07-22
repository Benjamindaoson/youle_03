from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agents.orchestrator_agent.langgraph_runner import compiler_step_node
from agents.orchestrator_agent.langgraph_runner.compiler_step_node import make_step_node
from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
from app.schemas.agent import AgentResult, ArtifactRef


def _state():
    return make_initial_state(
        task_id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        skill_yaml={},
        collected_fields={},
    )


@pytest.mark.asyncio
async def test_image_confirmation_happens_before_dispatch(monkeypatch) -> None:
    dispatched = []

    async def dispatch(task):
        dispatched.append(task)

    async def wait_for_result(task_id, step_id, timeout):
        return AgentResult(
            task_id=uuid4(),
            step_id=step_id,
            status="completed",
            output=ArtifactRef(artifact_id=uuid4(), type="image_collection", reference="oss://images"),
        )

    def pause(payload):
        assert payload["preview_artifact_metadata"]["image_count"] == 3
        return {"resolution": "approved", "user_choice": {"confirmed_image_count": 3}}

    monkeypatch.setattr(compiler_step_node, "interrupt", pause)
    node = make_step_node(
        {
            "step_id": "segment_images",
            "agent": "agent_3",
            "task_type": "batch_generate",
            "parameters": {
                "count": 3,
                "confirmation": {"model": "doubao-seedream-4-0-250828"},
            },
            "hitl_gate": {"type": "image_generation_confirmation", "phase": "before_dispatch"},
        },
        dispatcher=dispatch,
        result_waiter=wait_for_result,
    )

    await node(_state())

    assert len(dispatched) == 1
    assert dispatched[0].parameters["count"] == 3


@pytest.mark.asyncio
async def test_mismatched_image_confirmation_does_not_dispatch(monkeypatch) -> None:
    dispatched = AsyncMock()

    def pause(_payload):
        return {"resolution": "approved", "user_choice": {"confirmed_image_count": 2}}

    monkeypatch.setattr(compiler_step_node, "interrupt", pause)
    node = make_step_node(
        {
            "step_id": "segment_images",
            "agent": "agent_3",
            "task_type": "batch_generate",
            "parameters": {"count": 3},
            "hitl_gate": {"type": "image_generation_confirmation", "phase": "before_dispatch"},
        },
        dispatcher=dispatched,
        result_waiter=AsyncMock(),
    )

    update = await node(_state())

    assert dispatched.await_count == 0
    assert update["final_status"] == "failed"
    assert update["failure_reason"] == "image_generation_not_confirmed"
