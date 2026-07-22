"""Single-process, zero-provider Agent worker for the local core profile."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from agents._common.boundary import SUPPORTED_TASK_TYPES
from agents._common.consumer import AgentConsumer
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef


def _artifact_type(task_type: str) -> str:
    if "video" in task_type:
        return "video"
    if "image" in task_type:
        return "image"
    if any(token in task_type for token in ("audio", "bgm", "tts")):
        return "audio"
    if any(token in task_type for token in ("search", "extract", "data")):
        return "structured"
    return "text"


async def mock_task_handler(task: AgentTask) -> AgentResult:
    artifact_type = _artifact_type(task.task_type)
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type=artifact_type,
            reference=f"mock://{task.task_id}/{task.step_id}",
            extra_metadata={"mock": True, "external_model_calls": 0},
        ),
        cost_usd=0.0,
        model_used="mock/core",
    )


def build_consumers() -> list[AgentConsumer]:
    return [
        AgentConsumer(
            agent_id=agent_id,
            handlers={task_type: mock_task_handler for task_type in task_types},
            consumer_name=f"core-{agent_id}",
        )
        for agent_id, task_types in SUPPORTED_TASK_TYPES.items()
    ]


async def main() -> None:
    consumers = build_consumers()
    tasks = [asyncio.create_task(consumer.start()) for consumer in consumers]
    try:
        completed, _pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in completed:
            error = task.exception()
            if error is not None:
                raise error
        raise RuntimeError("Agent consumer exited unexpectedly")
    finally:
        for consumer in consumers:
            consumer.stop()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
