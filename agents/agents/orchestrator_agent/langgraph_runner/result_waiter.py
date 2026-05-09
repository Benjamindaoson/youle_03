"""LangGraph 节点等 Agent 回执的 utility。

每个 step 节点 await `wait_for_step_result(task_id, step_id, timeout_s)` →
读 `agent_results:<task_id>` Redis Stream,过滤匹配 step_id 的回执。

游标存 Redis Hash (agent_result_cursors:<task_id>  field=step_id  value=last_id)
而非进程内 dict,确保多 worker 部署时 start / resume 路由到不同 worker 也能续读。
"""

from __future__ import annotations

import asyncio
import json

import structlog

from app.redis_client import get_redis
from app.schemas.agent import AgentResult

log = structlog.get_logger(__name__)

_CURSOR_KEY_PREFIX = "agent_result_cursors"
_CURSOR_TTL = 86400  # 24h — 足够覆盖最长任务生命周期


async def _get_cursor(task_id: str, step_id: str) -> str:
    redis = await get_redis()
    val = await redis.hget(f"{_CURSOR_KEY_PREFIX}:{task_id}", step_id)
    return val or "0"


async def _set_cursor(task_id: str, step_id: str, cursor: str) -> None:
    redis = await get_redis()
    key = f"{_CURSOR_KEY_PREFIX}:{task_id}"
    await redis.hset(key, step_id, cursor)
    await redis.expire(key, _CURSOR_TTL)


async def reset_cursor(task_id: str, step_id: str) -> None:
    """time-travel 回滚后,重置某 step 的 cursor 让它能重新等回执。"""
    redis = await get_redis()
    await redis.hdel(f"{_CURSOR_KEY_PREFIX}:{task_id}", step_id)


async def wait_for_step_result(
    task_id: str, step_id: str, timeout_s: int
) -> AgentResult | None:
    """阻塞等指定 step 的 AgentResult。

    其它 step 的回执不会丢,会留在 stream 给别的节点消费(下一次 read 时拿到)。
    """
    stream = f"agent_results:{task_id}"
    deadline = asyncio.get_event_loop().time() + max(5, timeout_s)
    last_id = await _get_cursor(task_id, step_id)

    while asyncio.get_event_loop().time() < deadline:
        redis = await get_redis()
        try:
            resp = await redis.xread({stream: last_id}, block=2000, count=10)
        except Exception as e:
            log.warning("lg.waiter.read_failed", err=str(e))
            await asyncio.sleep(1)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                await _set_cursor(task_id, step_id, last_id)
                try:
                    payload = json.loads(fields["data"])
                    result = AgentResult.model_validate(payload)
                except Exception as e:
                    log.warning("lg.waiter.parse_failed", err=str(e))
                    continue
                if result.step_id == step_id:
                    return result
    return None
