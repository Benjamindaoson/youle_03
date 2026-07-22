from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agents._common.protocol import AgentTask
from agents.document_agent import main as document_main
from agents.document_agent.handlers import image_concat_long as handler_module
from agents.document_agent.handlers.image_concat_long import image_concat_long_handler


def test_document_agent_registers_long_image_concat() -> None:
    assert document_main._build_handlers()["image_concat_long"] is image_concat_long_handler


@pytest.mark.asyncio
async def test_concat_reads_upstream_image_refs(monkeypatch) -> None:
    concat = AsyncMock(return_value="oss://haole-dev/long.png")
    monkeypatch.setattr(handler_module, "concat_long_local", concat)
    task = AgentTask(
        task_id=uuid4(),
        step_id="long_concat",
        agent_id="agent_2",
        task_type="image_concat_long",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={
            "images": {
                "reference": "oss://manifest.json",
                "metadata": {"image_refs": ["oss://a.png", "oss://b.png"]},
            }
        },
    )

    result = await image_concat_long_handler(task)

    assert result.status == "completed"
    assert result.output is not None
    assert result.output.reference == "oss://haole-dev/long.png"
    concat.assert_awaited_once_with(["oss://a.png", "oss://b.png"], direction="vertical")
