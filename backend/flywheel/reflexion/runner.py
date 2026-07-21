"""信号 3:失败 / 用户负反馈 → Reflexion → prompt_improvement_candidates(人审)。

V1.5:LangGraph 化(参见 ADR-017)。
本模块只负责"订阅 Stream + 转给 graph",真实状态机在
`orchestrator.langgraph_runner.reflexion_graph` 里。

收益:
- LLM 失败 → checkpoint 保留,人工排查后可 ainvoke(None) 续跑
- analyze / validate / persist 三段独立,可单步重试
- thread_id = task_id,UI 可拉历史
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import redis.asyncio as aioredis
import structlog
from agents.orchestrator_agent.langgraph_runner.reflexion_graph import process_reflexion_event

log = structlog.get_logger(__name__)


async def _process(payload: dict[str, Any]) -> None:
    """转 LangGraph reflexion graph(替代单步内联)。"""
    out = await process_reflexion_event(payload)
    if out.get("error"):
        log.warning("flywheel.reflexion.graph_error", **out)
    else:
        log.info("flywheel.reflexion.graph_done", **out)


async def main() -> None:
    redis = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )
    last_id = "$"  # 只接 runner 启动后的新事件
    while True:
        try:
            resp = await redis.xread(
                {"flywheel:signals": last_id}, block=5000, count=10
            )
        except Exception as e:
            log.warning("flywheel.reflexion.xread_failed", err=str(e))
            await asyncio.sleep(2)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                if fields.get("type") != "reflexion":
                    continue
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except json.JSONDecodeError:
                    continue
                await _process(payload)


if __name__ == "__main__":
    asyncio.run(main())
