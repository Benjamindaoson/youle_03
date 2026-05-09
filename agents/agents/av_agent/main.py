"""Agent 4(影音师)进程入口 — ReAct Worker + Redis Streams。"""

from __future__ import annotations

import asyncio

from agents._common.consumer import AgentConsumer
from agents._common.react_personas import get_persona


async def main() -> None:
    consumer = AgentConsumer(
        agent_id="agent_4",
        handlers={},
        persona=get_persona("agent_4"),
    )
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
