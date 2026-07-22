"""Agent 2 document worker entry point."""

from __future__ import annotations

import asyncio

from agents._common.consumer import AgentConsumer
from agents._common.react_personas import get_persona
from agents.document_agent.handlers.image_concat_long import image_concat_long_handler


def _build_handlers() -> dict[str, object]:
    return {"image_concat_long": image_concat_long_handler}


async def main() -> None:
    consumer = AgentConsumer(
        agent_id="agent_2",
        handlers=_build_handlers(),
        persona=get_persona("agent_2"),
    )
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())

