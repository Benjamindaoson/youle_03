from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agents._common.protocol import AgentTask
from agents.image_agent.handlers import ark_seedream
from agents.image_agent.handlers.batch_generate import batch_generate_handler


@pytest.mark.asyncio
async def test_ecommerce_batch_uses_seedream_once_per_confirmed_image(monkeypatch) -> None:
    calls = AsyncMock(
        side_effect=[
            ark_seedream.SeedreamImageResult(url="https://img.example/a.jpg", model="seedream"),
            ark_seedream.SeedreamImageResult(url="https://img.example/b.jpg", model="seedream"),
        ]
    )
    monkeypatch.setattr(ark_seedream, "generate_seedream_image", calls)
    monkeypatch.setattr(
        "agents.image_agent.handlers.batch_generate._normalize_image_artifact",
        AsyncMock(side_effect=[("oss://a", "downloaded_url"), ("oss://b", "downloaded_url")]),
    )
    monkeypatch.setattr("agents.image_agent.handlers.batch_generate.put_json", AsyncMock(return_value="oss://manifest"))
    monkeypatch.setattr("agents.image_agent.handlers.batch_generate.emit", AsyncMock())
    monkeypatch.setattr("agents.image_agent.handlers.batch_generate.get_user_prefs", AsyncMock(return_value={}))

    task = AgentTask(
        task_id=uuid4(),
        step_id="segment_images",
        agent_id="agent_3",
        task_type="batch_generate",
        user_id=uuid4(),
        conversation_id=uuid4(),
        parameters={
            "count": 2,
            "image_specs": [{"prompt": "first", "size": "2K"}, {"prompt": "second", "size": "2K"}],
        },
        routing_hints={"provider": "ark_seedream", "no_retry": True, "no_fallback": True},
    )

    result = await batch_generate_handler(task)

    assert result.status == "completed"
    assert calls.await_count == 2
    assert result.output is not None
    assert result.output.extra_metadata["count"] == 2
