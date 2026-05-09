"""Agent 侧可轮询的取消标志 — 与 DB 任务取消联动(长耗时 handler 用)。"""

from __future__ import annotations

from uuid import UUID

from app.redis_client import get_redis

CANCEL_KEY_PREFIX = "agent_cancel"


async def publish_agent_task_cancel(task_id: UUID | str, *, ttl_seconds: int = 3600) -> None:
    """用户取消任务时 backend 写入,Worker 内轮询 `exists` 即可提前退出。"""
    redis = await get_redis()
    await redis.setex(f"{CANCEL_KEY_PREFIX}:{task_id}", ttl_seconds, "1")
