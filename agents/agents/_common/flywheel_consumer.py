"""飞轮信号消费者进程 — 读 flywheel:signals Redis Stream,路由到 Redis 存储层。

4 类信号:
  trace      → Redis Hash flywheel:stats:{user_id}  (任务统计)
  preference → Redis Hash flywheel:prefs:{user_id}  (风格偏好,可被 handler 注入)
  reflexion  → Redis Stream flywheel:reflexion       (反思日志,供 Skill 优化)
  skill_draft → Redis Stream flywheel:skill_drafts  (Skill 草稿,供人工审核)

运行: python -m agents._common.flywheel_consumer
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CONSUMER_GROUP = "flywheel-processor"
CONSUMER_NAME = "flywheel-consumer-1"
STREAM_KEY = "flywheel:signals"
PREF_TTL_SECONDS = 7 * 24 * 3600  # 1 week


async def _ensure_group(redis: aioredis.Redis) -> None:
    try:
        await redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise


async def _handle_preference(redis: aioredis.Redis, payload: dict[str, Any]) -> None:
    """Store style/mood preferences from style_extract signals."""
    user_id = str(payload.get("user_id") or payload.get("task_id", "unknown"))
    key = f"flywheel:prefs:{user_id}"

    mood_list = payload.get("mood", [])
    if isinstance(mood_list, list):
        for mood in mood_list:
            if mood:
                await redis.hincrby(key, f"mood_count:{mood}", 1)

    if payload.get("prompt_inject"):
        await redis.hset(key, "last_prompt_inject", str(payload["prompt_inject"])[:200])

    if payload.get("style_pref"):
        await redis.hset(key, "style_pref", str(payload["style_pref"]))

    await redis.expire(key, PREF_TTL_SECONDS)


async def _handle_trace(redis: aioredis.Redis, payload: dict[str, Any]) -> None:
    """Accumulate task trace stats per user."""
    user_id = str(payload.get("user_id") or payload.get("task_id", "unknown"))
    task_type = str(payload.get("task_type", "unknown"))
    key = f"flywheel:stats:{user_id}"

    await redis.hincrby(key, f"count:{task_type}", 1)

    for field in ("char_count", "layer_count", "total", "passed"):
        if payload.get(field) is not None:
            await redis.hincrby(key, f"{task_type}:{field}", int(payload[field]))

    await redis.expire(key, PREF_TTL_SECONDS)


async def _handle_reflexion(redis: aioredis.Redis, payload: dict[str, Any]) -> None:
    """Buffer reflexion signals for future Skill improvement pipeline."""
    await redis.xadd(
        "flywheel:reflexion",
        {"payload": json.dumps(payload, ensure_ascii=False)},
        maxlen=2000,
        approximate=True,
    )


async def _handle_skill_draft(redis: aioredis.Redis, payload: dict[str, Any]) -> None:
    """Buffer skill draft proposals for human review."""
    await redis.xadd(
        "flywheel:skill_drafts",
        {"payload": json.dumps(payload, ensure_ascii=False)},
        maxlen=500,
        approximate=True,
    )


_HANDLERS = {
    "preference": _handle_preference,
    "trace": _handle_trace,
    "reflexion": _handle_reflexion,
    "skill_draft": _handle_skill_draft,
}


async def run_consumer() -> None:
    redis: aioredis.Redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(redis)
    log.info("flywheel_consumer.started", stream=STREAM_KEY, group=CONSUMER_GROUP)

    while True:
        try:
            messages = await redis.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=50,
                block=2000,
            )
            if not messages:
                await asyncio.sleep(0)
                continue

            for _stream, entries in messages:
                for msg_id, fields in entries:
                    try:
                        signal_type = fields.get("type", "")
                        raw_payload = fields.get("payload", "{}")
                        payload: dict[str, Any] = json.loads(raw_payload)
                        handler = _HANDLERS.get(signal_type)
                        if handler:
                            await handler(redis, payload)
                        else:
                            log.debug("flywheel_consumer.unknown_type", signal_type=signal_type)
                        await redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                    except Exception as e:
                        log.warning("flywheel_consumer.msg_error", msg_id=msg_id, err=str(e))

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("flywheel_consumer.loop_error", err=str(e))
            await asyncio.sleep(5)

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run_consumer())
