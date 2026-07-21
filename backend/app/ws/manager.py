"""WebSocket connections backed by the shared per-user EventBus."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from typing import Any

import structlog
from fastapi import WebSocket

log = structlog.get_logger(__name__)


class WSManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._forwarders: dict[str, asyncio.Task[None]] = {}

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].add(ws)
            if user_id not in self._queues:
                from app.services.event_bus import event_bus

                queue = await event_bus.subscribe(user_id)
                self._queues[user_id] = queue
                self._forwarders[user_id] = asyncio.create_task(
                    self._forward_user(user_id, queue),
                    name=f"youle-ws-{user_id}",
                )

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        queue: asyncio.Queue[dict[str, Any]] | None = None
        forwarder: asyncio.Task[None] | None = None
        async with self._lock:
            self._connections[user_id].discard(ws)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)
                queue = self._queues.pop(user_id, None)
                forwarder = self._forwarders.pop(user_id, None)
        if queue is not None:
            from app.services.event_bus import event_bus

            await event_bus.unsubscribe(user_id, queue)
        if forwarder is not None:
            forwarder.cancel()
            with suppress(asyncio.CancelledError):
                await forwarder

    async def send_to_user(self, user_id: str, payload: dict[str, Any]) -> None:
        """本进程内推。跨进程请用 publish。"""
        for ws in list(self._connections.get(user_id, ())):
            try:
                await ws.send_json(payload)
            except Exception as e:
                log.warning("ws.send_failed", user_id=user_id, err=str(e))

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        """Compatibility adapter to the canonical business event publisher."""
        from app.services.event_publisher import event_publisher

        await event_publisher.publish_legacy(user_id, payload)

    async def _forward_user(
        self, user_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        while True:
            await self.send_to_user(user_id, await queue.get())


ws_manager = WSManager()
