"""MCP client 单测(用 respx mock HTTP)。"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.mcp_client import MCPClient, MCPError


@pytest.mark.asyncio
async def test_call_tool_happy_path() -> None:
    client = MCPClient(endpoints={"search": "http://mcp-search:7001"})
    with respx.mock(base_url="http://mcp-search:7001") as mock:
        mock.post("/tools/web_search").mock(
            return_value=Response(200, json={"results": [{"title": "x", "url": "y"}]})
        )
        out = await client.call_tool(
            server="search", tool="web_search", arguments={"query": "反诈"}
        )
        assert out["results"][0]["title"] == "x"
    await client.aclose()


@pytest.mark.asyncio
async def test_unknown_server_raises() -> None:
    client = MCPClient(endpoints={"search": "http://mcp-search:7001"})
    with pytest.raises(MCPError):
        await client.call_tool(server="nonexistent", tool="t", arguments={})
    await client.aclose()
