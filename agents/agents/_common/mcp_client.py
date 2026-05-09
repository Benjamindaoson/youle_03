"""Agent 端 MCP 客户端 — retry + Redis cache + result validation。

改进点(相对原版):
- 3 次指数退避重试(0.5s / 1.5s / 3s),仅 5xx 和网络错误重试
- Redis-backed 结果缓存(TTL 按 server 配置,search 5 min / document 30 min)
- 结果校验:非 dict / MCP error shape → _failed=True 而不是崩溃
- call_tool 永远返回 dict,不抛异常(降级策略由 handler 决定)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

MCP_ENDPOINTS: dict[str, str] = {
    "search": os.getenv("MCP_SEARCH_URL", "http://mcp-search:7001"),
    "image_tools": os.getenv("MCP_IMAGE_TOOLS_URL", "http://mcp-image-tools:7002"),
    "video_tools": os.getenv("MCP_VIDEO_TOOLS_URL", "http://mcp-video-tools:7003"),
    "audio_tools": os.getenv("MCP_AUDIO_TOOLS_URL", "http://mcp-audio-tools:7004"),
    "document_tools": os.getenv("MCP_DOCUMENT_TOOLS_URL", "http://mcp-document-tools:7005"),
    "oss": os.getenv("MCP_OSS_URL", "http://mcp-oss:7006"),
    "platform_publish": os.getenv("MCP_PLATFORM_PUBLISH_URL", "http://mcp-platform-publish:7007"),
}

# Cache TTL (seconds) per server; 0 = no cache
_CACHE_TTL: dict[str, int] = {
    "search": 300,          # 5 min — search results are stable
    "document_tools": 1800, # 30 min — extracted text doesn't change
    "image_tools": 0,
    "audio_tools": 0,
    "video_tools": 0,
    "oss": 0,
    "platform_publish": 0,
}

_MAX_RETRIES = 3
_RETRY_BACKOFF = (0.5, 1.5, 3.0)


def _cache_key(server: str, tool: str, arguments: dict[str, Any]) -> str:
    raw = json.dumps({"s": server, "t": tool, "a": arguments}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"mcp:cache:{digest}"


class AgentMCPClient:
    def __init__(self) -> None:
        # MCP sidecars 在内网;allow_internal=True 只拦截 cloud metadata 等
        # 永久黑名单(防 prompt injection 把请求带去 169.254.169.254 等)。
        try:
            from app.utils.httpx_safe import safe_async_client_kwargs
            extra = safe_async_client_kwargs(allow_internal=True)
        except Exception:
            extra = {}
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=5.0),
            **extra,
        )
        self._redis: Any = None  # aioredis.Redis | False | None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                log.debug("mcp_client.redis_unavailable", err=str(e))
                self._redis = False
        return self._redis if self._redis is not False else None

    def _validate_result(self, server: str, tool: str, result: Any) -> dict[str, Any]:
        """Normalize and validate MCP tool result."""
        if not isinstance(result, dict):
            log.warning("mcp_client.non_dict_response", server=server, tool=tool, type=type(result).__name__)
            return {"_failed": True, "error": "non_dict_response"}

        # MCP error envelope shapes
        if result.get("error") or result.get("isError"):
            log.warning("mcp_client.tool_error_response", server=server, tool=tool,
                        error=result.get("error") or result.get("content"))
            return {**result, "_failed": True}

        return result

    async def call_tool(self, *, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ttl = _CACHE_TTL.get(server, 0)
        cache_key = _cache_key(server, tool, arguments) if ttl > 0 else None

        # ── cache read ────────────────────────────────────────────────────────
        if cache_key:
            redis = await self._get_redis()
            if redis:
                try:
                    cached = await redis.get(cache_key)
                    if cached:
                        log.debug("mcp_client.cache_hit", server=server, tool=tool)
                        return json.loads(cached)
                except Exception as e:
                    log.debug("mcp_client.cache_read_error", err=str(e))

        url = f"{MCP_ENDPOINTS[server]}/tools/{tool}"
        last_err: Exception | None = None

        # ── retry loop ────────────────────────────────────────────────────────
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._http.post(url, json={"arguments": arguments})
                resp.raise_for_status()
                result = self._validate_result(server, tool, resp.json())

                # ── cache write ───────────────────────────────────────────────
                if cache_key and not result.get("_failed"):
                    redis = await self._get_redis()
                    if redis:
                        try:
                            await redis.setex(cache_key, ttl, json.dumps(result, ensure_ascii=False))
                        except Exception:
                            pass

                return result

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_err = e
                if attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF[attempt]
                    log.warning("mcp_client.retry", server=server, tool=tool,
                                attempt=attempt + 1, wait=wait, err=str(e))
                    await asyncio.sleep(wait)

            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code < 500:
                    break  # 4xx → don't retry
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])

        log.error("mcp_client.failed_after_retries", server=server, tool=tool,
                  attempts=_MAX_RETRIES, err=str(last_err))
        return {"_failed": True, "error": str(last_err), "server": server, "tool": tool}

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._redis and self._redis is not False:
            try:
                await self._redis.aclose()
            except Exception:
                pass


mcp_client = AgentMCPClient()
