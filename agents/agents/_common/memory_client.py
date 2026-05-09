"""飞轮记忆读接口 — Agent handler 注入用户偏好上下文。

用法:
    from agents._common.memory_client import get_user_prefs, build_pref_context

    prefs = await get_user_prefs(str(task.user_id))
    pref_ctx = build_pref_context(prefs)
    # 注入到 LLM prompt 的 user 消息尾部
"""

from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PREF_KEY_PREFIX = "flywheel:prefs:"
STATS_KEY_PREFIX = "flywheel:stats:"

_redis: Any = None


async def _get_redis() -> Any:
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        except Exception as e:
            log.warning("memory_client.redis_unavailable", err=str(e))
            _redis = False
    return _redis if _redis else None


async def get_user_prefs(user_id: str) -> dict[str, Any]:
    """Return stored style/mood preferences for user_id.

    Returns empty dict if Redis is unavailable or user has no stored prefs.
    """
    redis = await _get_redis()
    if redis is None:
        return {}

    try:
        raw: dict[str, str] = await redis.hgetall(f"{PREF_KEY_PREFIX}{user_id}")
    except Exception as e:
        log.debug("memory_client.read_error", user_id=user_id[:8], err=str(e))
        return {}

    if not raw:
        return {}

    prefs: dict[str, Any] = {}
    mood_counts: dict[str, int] = {}

    for k, v in raw.items():
        if k.startswith("mood_count:"):
            mood = k[len("mood_count:"):]
            mood_counts[mood] = int(v)
        elif k == "last_prompt_inject":
            prefs["prompt_inject"] = v
        elif k == "style_pref":
            prefs["style_pref"] = v

    if mood_counts:
        prefs["top_moods"] = sorted(mood_counts, key=lambda m: mood_counts[m], reverse=True)[:3]

    return prefs


async def get_user_stats(user_id: str) -> dict[str, int]:
    """Return task count stats for user_id."""
    redis = await _get_redis()
    if redis is None:
        return {}

    try:
        raw: dict[str, str] = await redis.hgetall(f"{STATS_KEY_PREFIX}{user_id}")
        return {k: int(v) for k, v in raw.items()}
    except Exception:
        return {}


def build_pref_context(prefs: dict[str, Any]) -> str:
    """Format user preferences into a short string for prompt injection.

    Returns empty string if prefs is empty — handlers must handle this gracefully.
    """
    if not prefs:
        return ""

    parts: list[str] = []
    if prefs.get("top_moods"):
        moods_str = "、".join(prefs["top_moods"])
        parts.append(f"用户历史偏好风格: {moods_str}")
    if prefs.get("style_pref"):
        parts.append(f"风格偏好: {prefs['style_pref']}")
    if prefs.get("prompt_inject"):
        parts.append(f"参考风格描述: {prefs['prompt_inject']}")

    return "\n".join(parts)
