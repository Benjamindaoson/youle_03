"""Agent 4 audio_to_text handler 简单 happy path(mock LLM)。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from agents._common.protocol import AgentTask
from agents.av_agent.handlers.audio_to_text import audio_to_text_handler


@pytest.fixture
def fake_task() -> AgentTask:
    return AgentTask(
        task_id=uuid4(),
        step_id="step_audio",
        agent_id="agent_4",
        task_type="audio_to_text",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"audio_url": "oss://youle-dev/clips/sample.mp3"},
        parameters={"language": "zh"},
        routing_hints={},
    )


def test_handler_missing_audio_returns_failed() -> None:
    bad = AgentTask(
        task_id=uuid4(),
        step_id="x",
        agent_id="agent_4",
        task_type="audio_to_text",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={},
        parameters={},
        routing_hints={},
    )
    result = asyncio.run(audio_to_text_handler(bad))
    assert result.status == "failed"
    assert (result.error_detail or {}).get("reason") == "missing_audio_url"
