"""MCP 客户端封装(铁律 13 / ADR-009)。

工具集成唯一标准:Agent handler 通过 `mcp_client.call_tool(server, tool, arguments)` 调用。
禁止在 handler 里 `import tavily / from playwright import ...`。

V1 必上线 7 个 MCP server:
  search / image_tools / video_tools / audio_tools / document_tools / oss / platform_publish(V1.5)

stdio 模式启动 server 进程;HTTP 模式直接调子进程暴露的端点。
本文件提供轻量 client wrapper;实际生产用 mcp Python SDK。
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


# 7 个 MCP server 服务发现(dev 用 docker-compose service name)
MCP_ENDPOINTS: dict[str, str] = {
    "search": "http://mcp-search:7001",
    "image_tools": "http://mcp-image-tools:7002",
    "video_tools": "http://mcp-video-tools:7003",
    "audio_tools": "http://mcp-audio-tools:7004",
    "document_tools": "http://mcp-document-tools:7005",
    "oss": "http://mcp-oss:7006",
    "platform_publish": "http://mcp-platform-publish:7007",  # V1.5
}


class MCPError(Exception):
    pass


class MCPClient:
    def __init__(self, endpoints: dict[str, str] | None = None) -> None:
        self._endpoints = endpoints or MCP_ENDPOINTS
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))

    async def call_tool(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """调用 MCP tool。返回 JSON 结果或抛 MCPError。"""
        if server not in self._endpoints:
            raise MCPError(f"unknown MCP server: {server}")
        url = f"{self._endpoints[server]}/tools/{tool}"
        log.debug("mcp.call_tool", server=server, tool=tool)
        try:
            resp = await self._http.post(url, json={"arguments": arguments})
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            raise MCPError(f"{server}/{tool} -> HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise MCPError(f"{server}/{tool} -> {e}") from e

    async def list_tools(self, server: str) -> list[dict[str, Any]]:
        if server not in self._endpoints:
            raise MCPError(f"unknown MCP server: {server}")
        resp = await self._http.get(f"{self._endpoints[server]}/tools")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        await self._http.aclose()


_singleton: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _singleton
    if _singleton is None:
        _singleton = MCPClient()
    return _singleton


async def close_mcp_client() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.aclose()
        _singleton = None
