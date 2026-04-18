import json
import logging

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from pearl.mcp.server import MCPServer
from pearl.mcp.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

_TOOL_MAP: dict[str, dict] = {t["name"]: t for t in TOOL_DEFINITIONS}


def build_mcp_asgi_app(api_base_url: str, api_key: str | None = None):
    """Return a Starlette ASGI app for the MCP streamable HTTP transport.

    The returned app manages the StreamableHTTPSessionManager lifecycle via
    its own lifespan so that ``_task_group`` is always initialised before
    any request is dispatched.
    """
    pearl = MCPServer(base_url=api_base_url, api_key=api_key)
    server = Server("pearl-api")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[mcp_types.TextContent]:
        if name not in _TOOL_MAP:
            logger.warning("MCP HTTP unknown tool requested: %s", name)
            return [mcp_types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = await pearl.call_tool(name, arguments or {})
        except Exception as exc:
            logger.error("MCP HTTP tool %s failed: %s", name, exc)
            result = {"error": str(exc)}
        return [mcp_types.TextContent(type="text", text=json.dumps(result))]

    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
    )

    class _MCPApp:
        """Minimal ASGI wrapper that owns the session manager lifecycle."""

        async def __call__(self, scope, receive, send):
            if scope["type"] == "lifespan":
                # Forward lifespan events through our context manager
                await _MCPApp._lifespan_handler(scope, receive, send)
            else:
                await session_manager.handle_request(scope, receive, send)

        @staticmethod
        async def _lifespan_handler(scope, receive, send):
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                try:
                    async with session_manager.run():
                        await send({"type": "lifespan.startup.complete"})
                        await receive()  # wait for shutdown signal
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    raise

    return _MCPApp()
