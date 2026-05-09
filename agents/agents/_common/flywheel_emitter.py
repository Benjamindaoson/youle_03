"""Agent 端飞轮信号 emit(ADR-011)— Push 到 Redis Stream,主编排消费。"""

from __future__ import annotations

import json
import os
from typing import Any

import redis.asyncio as aioredis


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def emit(*, signal_type: str, payload: dict[str, Any]) -> None:
    """4 类信号:trace / preference / reflexion / skill_draft。"""
    redis = await _get_redis()
    await redis.xadd("flywheel:signals", {"type": signal_type, "payload": json.dumps(payload, ensure_ascii=False)})
