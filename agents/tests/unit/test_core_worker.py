from uuid import uuid4

import pytest

from agents._common.protocol import AgentTask
from agents.core_worker import build_consumers, mock_task_handler


def test_core_worker_builds_one_process_worth_of_all_agent_consumers() -> None:
    consumers = build_consumers()

    assert [consumer.agent_id for consumer in consumers] == [
        "agent_1",
        "agent_2",
        "agent_3",
        "agent_4",
    ]
    assert all(consumer.persona is None for consumer in consumers)


@pytest.mark.asyncio
async def test_core_worker_returns_zero_cost_video_without_provider_calls() -> None:
    task = AgentTask(
        task_id=uuid4(),
        step_id="video_compose",
        agent_id="agent_4",
        task_type="video_compose",
        user_id=uuid4(),
        conversation_id=uuid4(),
    )

    result = await mock_task_handler(task)

    assert result.status == "completed"
    assert result.output is not None
    assert result.output.type == "video"
    assert result.output.reference.startswith("mock://")
    assert result.output.extra_metadata["external_model_calls"] == 0
    assert result.cost_usd == 0.0
    assert result.model_used == "mock/core"


@pytest.mark.asyncio
async def test_consumer_socket_timeout_exceeds_blocking_read(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeRedis:
        async def xgroup_create(self, *_args, **_kwargs) -> None:
            return None

    def fake_from_url(_url: str, **kwargs):
        captured.update(kwargs)
        return FakeRedis()

    monkeypatch.setattr("agents._common.consumer.aioredis.from_url", fake_from_url)
    consumer = build_consumers()[0]

    await consumer._r()

    assert captured["socket_timeout"] > 5
