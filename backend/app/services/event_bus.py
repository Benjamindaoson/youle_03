"""Per-user event delivery for SSE and WebSocket clients."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from weakref import WeakSet

import structlog

log = structlog.get_logger(__name__)

_CHANNEL_PREFIX = "haole:events:"
_CHANNEL_PATTERN = f"{_CHANNEL_PREFIX}*"
_DEFAULT_QUEUE_MAXSIZE = 1000


class _EventJSONEncoder(json.JSONEncoder):
    def default(self, value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (set, frozenset)):
            return list(value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.hex()
        return super().default(value)


class EventBus:
    """Fan out user events locally and through one Redis Pub/Sub channel family."""

    def __init__(self, *, queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE) -> None:
        self._queue_maxsize = queue_maxsize
        self._subscribers: dict[
            str, WeakSet[asyncio.Queue[dict[str, Any]]]
        ] = defaultdict(WeakSet)
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task[None] | None = None
        self._listener_ready = asyncio.Event()
        self._redis_available = False

    async def start(self) -> None:
        """Start the Redis listener; local delivery remains available on failure."""
        if self._listener_task is not None and not self._listener_task.done():
            return
        self._listener_task = asyncio.create_task(
            self._listen_forever(), name="haole-event-bus"
        )
        try:
            await asyncio.wait_for(self._listener_ready.wait(), timeout=2.0)
        except TimeoutError:
            log.warning("event_bus.listener_start_timeout")

    async def stop(self) -> None:
        task = self._listener_task
        self._listener_task = None
        self._redis_available = False
        self._listener_ready.clear()
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def publish_to_user(self, user_id: str, payload: dict[str, Any]) -> None:
        """Publish through Redis, with local-only delivery as a safe fallback."""
        if self._redis_available:
            try:
                from app.redis_client import get_redis

                redis = await get_redis()
                encoded = json.dumps(payload, cls=_EventJSONEncoder, ensure_ascii=False)
                await redis.publish(f"{_CHANNEL_PREFIX}{user_id}", encoded)
                return
            except Exception as exc:  # noqa: BLE001 - Redis failure degrades locally
                log.warning(
                    "event_bus.redis_publish_failed",
                    user_id=user_id,
                    event_type=payload.get("type"),
                    err=str(exc),
                )
        await self._deliver_local(user_id, payload)

    async def subscribe(self, user_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=self._queue_maxsize
        )
        async with self._lock:
            self._subscribers[user_id].add(queue)
        return queue

    async def unsubscribe(
        self, user_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        async with self._lock:
            queues = self._subscribers.get(user_id)
            if queues is None:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(user_id, None)

    def subscriber_count(self, user_id: str) -> int:
        return len(self._subscribers.get(user_id, ()))

    async def _deliver_local(self, user_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(user_id, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    log.warning("event_bus.queue_drop", user_id=user_id)

    async def _listen_forever(self) -> None:
        from app.redis_client import get_redis

        backoff = 0.5
        while True:
            pubsub = None
            try:
                redis = await get_redis()
                pubsub = redis.pubsub(ignore_subscribe_messages=True)
                await pubsub.psubscribe(_CHANNEL_PATTERN)
                self._redis_available = True
                self._listener_ready.set()
                backoff = 0.5
                async for message in pubsub.listen():
                    if message.get("type") not in {"message", "pmessage"}:
                        continue
                    channel = message.get("channel", "")
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    if not isinstance(channel, str) or not channel.startswith(
                        _CHANNEL_PREFIX
                    ):
                        continue
                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        payload = json.loads(raw) if isinstance(raw, str) else raw
                    except (TypeError, ValueError):
                        log.warning("event_bus.invalid_payload", channel=channel)
                        continue
                    if isinstance(payload, dict):
                        await self._deliver_local(
                            channel[len(_CHANNEL_PREFIX) :], payload
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect indefinitely
                self._redis_available = False
                self._listener_ready.set()
                log.warning(
                    "event_bus.listener_failed", err=str(exc), backoff=backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)
            finally:
                if pubsub is not None:
                    with suppress(Exception):
                        await pubsub.punsubscribe(_CHANNEL_PATTERN)
                    with suppress(Exception):
                        await pubsub.aclose()


event_bus = EventBus()
