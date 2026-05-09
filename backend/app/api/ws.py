"""WebSocket 端点 + 心跳。

# 鉴权模式(安全升级)
推荐:连接后第一条消息发 {"type": "auth", "token": "<jwt>"},
     token 不出现在 URL,规避服务器访问日志/浏览器历史泄漏。

兼容:URL query param ?token=<jwt> 仍接受(旧客户端迁移期),
     但服务端会在日志中打 deprecation warning。
"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.ws.manager import ws_manager

router = APIRouter()
log = structlog.get_logger(__name__)

# 等待客户端发送 auth 消息的超时时间(秒)
_AUTH_MESSAGE_TIMEOUT_S = 10


class WebSocketAuthError(Exception):
    """JWT 非法或校验失败。"""


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str | None = None) -> None:
    """支持两种鉴权模式:协议内首条消息(推荐) / URL query param(兼容旧版)。"""
    # 先 accept,再做协议内鉴权,token 不再强制出现在 URL
    await websocket.accept()

    # _session_token 保存有效 JWT 供 M-7 中期重校验使用
    _session_token: str | None = None

    try:
        if token:
            # 旧客户端:URL query param 传 token(兼容)
            log.warning("ws.token_in_url_deprecated",
                        note="Pass token in first auth message instead")
            try:
                user_id = await _validate_token(token)
                _session_token = token
            except WebSocketAuthError:
                await websocket.close(code=4401)
                return
        else:
            # 新模式:等待首条 {"type": "auth", "token": "..."} 消息
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_AUTH_MESSAGE_TIMEOUT_S
                )
                msg = json.loads(raw)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "error", "code": "auth_timeout"})
                await websocket.close(code=4401)
                return
            except Exception:
                await websocket.send_json({"type": "error", "code": "invalid_message"})
                await websocket.close(code=4401)
                return

            if msg.get("type") == "ping":
                # 客户端先发 ping(心跳优先) → 视为 anonymous
                await websocket.send_json({"type": "pong"})
                user_id = "anonymous"
            elif msg.get("type") == "auth" and msg.get("token"):
                try:
                    _session_token = msg["token"]
                    user_id = await _validate_token(_session_token)
                except WebSocketAuthError:
                    await websocket.send_json({"type": "error", "code": "auth_failed"})
                    await websocket.close(code=4401)
                    return
                await websocket.send_json({"type": "auth_ok", "user_id": user_id})
            else:
                user_id = "anonymous"
    except WebSocketDisconnect:
        return

    await ws_manager.register(user_id, websocket)
    log.info("ws.connect", user_id=user_id)

    # M-7: 每 N 次心跳重校验 token 是否过期
    _heartbeat_count = 0
    _REAUTH_EVERY_N = 10  # 每 10 次心跳重校验一次(约 5 分钟,取决于 WS_HEARTBEAT_SECONDS)

    try:
        while True:
            recv = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait(
                {recv}, timeout=settings.WS_HEARTBEAT_SECONDS
            )
            if recv in done:
                msg_text = recv.result()
                if msg_text == "ping":
                    await websocket.send_json({"type": "pong"})
            else:
                recv.cancel()
                await websocket.send_json({"type": "pong"})  # 服务端主动心跳

            # 周期性 token 过期检查(仅对有效 JWT 用户,anonymous 跳过)
            if _session_token and user_id != "anonymous":
                _heartbeat_count += 1
                if _heartbeat_count % _REAUTH_EVERY_N == 0:
                    try:
                        await _validate_token(_session_token)
                    except WebSocketAuthError:
                        log.info("ws.token_expired_mid_session", user_id=user_id)
                        await websocket.send_json({"type": "error", "code": "token_expired"})
                        await websocket.close(code=4401)
                        break
    except WebSocketDisconnect:
        log.info("ws.disconnect", user_id=user_id)
    finally:
        await ws_manager.unregister(user_id, websocket)


async def _validate_token(token: str) -> str:
    """校验 JWT,返回 user_id 字符串;无效则抛 WebSocketAuthError。"""
    from fastapi import HTTPException
    from app.api.auth import decode_token

    try:
        return str(decode_token(token.strip()))
    except HTTPException as e:
        log.warning(
            "ws.token_rejected",
            detail=getattr(e, "detail", "invalid_token"),
        )
        raise WebSocketAuthError from e


# 保持旧名兼容(部分测试直接调 _resolve_user)
async def _resolve_user(token: str | None) -> str:
    if not token or not str(token).strip():
        return "anonymous"
    return await _validate_token(token)
