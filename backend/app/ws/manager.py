"""WS 连接管理 + Redis Pub/Sub 跨实例广播。"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

import structlog
from fastapi import WebSocket

from app.redis_client import get_redis

log = structlog.get_logger(__name__)


class WSManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task[None] | None = None

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].add(ws)
            if self._listener_task is None:
                self._listener_task = asyncio.create_task(self._listen_pubsub())

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].discard(ws)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict[str, Any]) -> None:
        """本进程内推。跨进程请用 publish。"""
        msg = json.dumps(payload, ensure_ascii=False, default=str)
        for ws in list(self._connections.get(user_id, ())):
            try:
                await ws.send_text(msg)
            except Exception as e:
                log.warning("ws.send_failed", user_id=user_id, err=str(e))

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        """跨进程广播 — 通过 Redis Pub/Sub。"""
        redis = await get_redis()
        await redis.publish("youle.ws", json.dumps({"user_id": user_id, "payload": payload}))

    async def _listen_pubsub(self) -> None:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe("youle.ws")
        log.info("ws.pubsub.listening")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await self.send_to_user(data["user_id"], data["payload"])
            except Exception as e:
                log.warning("ws.pubsub.error", err=str(e))


ws_manager = WSManager()
