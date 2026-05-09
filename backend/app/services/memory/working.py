"""短期工作记忆(Redis TTL) — 可选,失败静默。"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

KEY_PREFIX = "mem:wk"
DEFAULT_TTL = 3600


def working_key(conversation_id: UUID, slot: str) -> str:
    return f"{KEY_PREFIX}:{conversation_id}:{slot}"


async def working_set(conversation_id: UUID, slot: str, payload: dict[str, Any], ttl: int = DEFAULT_TTL) -> None:
    try:
        from app.redis_client import get_redis

        r = await get_redis()
        await r.set(working_key(conversation_id, slot), json.dumps(payload, ensure_ascii=False), ex=ttl)
    except Exception as e:
        log.debug("memory.working_set_skip", err=str(e))


async def working_get(conversation_id: UUID, slot: str) -> dict[str, Any] | None:
    try:
        from app.redis_client import get_redis

        r = await get_redis()
        raw = await r.get(working_key(conversation_id, slot))
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        log.debug("memory.working_get_skip", err=str(e))
        return None
