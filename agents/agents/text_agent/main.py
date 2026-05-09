"""Agent 1(文字)进程 — 注册业务 handlers + ReAct 兜底。"""

from __future__ import annotations

import asyncio

from agents._common.consumer import AgentConsumer
from agents._common.react_personas import get_persona
from agents.text_agent.handlers.extras import (
    analysis_handler,
    polish_handler,
    structured_writing_handler,
    summarization_handler,
    translation_handler,
)
from agents.text_agent.handlers.long_writing import long_writing_handler
from agents.text_agent.handlers.short_writing import short_writing_handler
from agents.text_agent.handlers.version_compare import version_compare_handler
from agents.text_agent.handlers.web_search import web_search_handler


async def main() -> None:
    consumer = AgentConsumer(
        agent_id="agent_1",
        handlers={
            "web_search": web_search_handler,
            "long_writing": long_writing_handler,
            "short_video_script": long_writing_handler,
            "short_writing": short_writing_handler,
            "version_compare": version_compare_handler,
            "structured_writing": structured_writing_handler,
            "summarization": summarization_handler,
            "analysis": analysis_handler,
            "translation": translation_handler,
            "polish": polish_handler,
            "xhs_carousel_plan": structured_writing_handler,
            "xhs_carousel_copy": long_writing_handler,
            "xhs_delivery_summary": short_writing_handler,
        },
        persona=get_persona("agent_1"),
    )
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
