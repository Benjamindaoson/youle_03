"""每个 MCP server 共用的 HTTP 适配(FastAPI),将 tool 注册成 POST /tools/<name>。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def make_app(*, server_name: str, tools: dict[str, ToolFn]) -> FastAPI:
    app = FastAPI(title=f"mcp-{server_name}")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "server": server_name}

    @app.get("/tools")
    async def list_tools() -> list[dict[str, str]]:
        return [{"name": name} for name in tools]

    for name, fn in tools.items():
        async def _handler(body: dict[str, Any], _fn: ToolFn = fn) -> dict[str, Any]:
            return await _fn(body.get("arguments", {}))

        app.add_api_route(
            f"/tools/{name}",
            _handler,
            methods=["POST"],
            name=f"tool_{name}",
        )

    return app
