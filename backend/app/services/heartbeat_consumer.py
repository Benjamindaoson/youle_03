"""Agent 心跳消费器(v4 §11 拟人化 - 4 状态实时上报)。

每个 Agent worker 每 N 秒往 Redis Stream `agent_heartbeats` 写一条:
    { agent_id, status, ts, consumer, user_id }

本 consumer 把心跳折叠到 DB(agent_status 表),并通过 ws_manager 推送
AGENT_STATUS_CHANGED 事件。Idle/working 切换才触发推送(降噪)。

启动:
    asyncio.run(heartbeat_consumer.run())
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from app.db import SessionLocal
from app.services.agent_status import set_status

log = structlog.get_logger(__name__)

STREAM = "agent_heartbeats"
GROUP = "agent_heartbeats:writer"


async def _ensure_group(redis: aioredis.Redis) -> None:
    try:
        await redis.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def _process(fields: dict[str, str]) -> None:
    agent_id = fields.get("agent_id")
    status = fields.get("status") or "idle"
    user_id_raw = fields.get("user_id") or ""
    if not agent_id or not user_id_raw:
        return
    try:
        user_id = UUID(user_id_raw)
    except ValueError:
        return
    if status not in ("working", "idle", "fishing", "training"):
        return
    async with SessionLocal() as session:
        await set_status(
            session,
            user_id=user_id,
            agent_id=agent_id,
            status=status,  # type: ignore[arg-type]
        )


async def run() -> None:
    redis = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )
    await _ensure_group(redis)
    consumer_name = f"heartbeat-{os.getpid()}"
    log.info("heartbeat.consumer.start", consumer=consumer_name)
    while True:
        try:
            resp = await redis.xreadgroup(
                GROUP,
                consumer_name,
                streams={STREAM: ">"},
                count=20,
                block=5000,
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("heartbeat.consumer.read_error", err=str(e))
            await asyncio.sleep(2)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                try:
                    await _process(fields)
                except Exception as e:
                    log.warning("heartbeat.consumer.process_error", err=str(e))
                finally:
                    with contextlib.suppress(Exception):
                        await redis.xack(STREAM, GROUP, msg_id)


if __name__ == "__main__":
    asyncio.run(run())
