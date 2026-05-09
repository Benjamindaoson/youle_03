"""Agent 派活与回执消费(铁律 1:单一调度者通过 Redis Streams)。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.redis_client import get_redis
from app.schemas.agent import AgentResult, AgentTask

log = structlog.get_logger(__name__)

QUEUE_BY_AGENT = {
    "agent_1": "agent_tasks:text",
    "agent_2": "agent_tasks:document",
    "agent_3": "agent_tasks:image",
    "agent_4": "agent_tasks:av",
}


async def dispatch_task(task: AgentTask) -> str:
    """把 AgentTask 推到对应队列。返回 stream message id。"""
    redis = await get_redis()
    queue = QUEUE_BY_AGENT[task.agent_id]
    msg_id = await redis.xadd(queue, {"data": task.model_dump_json()})
    log.info("dispatcher.dispatched", task_id=str(task.task_id), step_id=task.step_id, queue=queue)
    return msg_id


async def wait_for_result(
    task_id: str, *, timeout_seconds: int = 120
) -> AgentResult | None:
    """阻塞等待该 task 的回执(单 step)。"""
    redis = await get_redis()
    stream = f"agent_results:{task_id}"
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last_id = "0"
    while asyncio.get_event_loop().time() < deadline:
        resp = await redis.xread({stream: last_id}, block=2000, count=1)
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                payload = json.loads(fields["data"])
                return AgentResult.model_validate(payload)
    return None


async def consume_results_loop(*, on_result: Any) -> None:
    """长驻消费 agent_results:* 的兜底 reaper(Sprint 4 接 LangGraph 后由 graph 自己消费)。"""
    redis = await get_redis()
    last_ids: dict[str, str] = {}
    while True:
        # 简化:扫一次当前已知的 result streams;真实用 keyspace notifications 或 PSUBSCRIBE
        keys = await redis.keys("agent_results:*")
        if not keys:
            await asyncio.sleep(2)
            continue
        streams = {k: last_ids.get(k, "0") for k in keys}
        resp = await redis.xread(streams, block=2000, count=10)
        if not resp:
            continue
        for stream, messages in resp:
            for msg_id, fields in messages:
                last_ids[stream] = msg_id
                try:
                    result = AgentResult.model_validate_json(fields["data"])
                    await on_result(result)
                except Exception as e:
                    log.warning("dispatcher.consume.parse_error", err=str(e))
