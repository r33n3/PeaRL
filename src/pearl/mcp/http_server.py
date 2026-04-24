import json
import structlog

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from pearl.mcp.server import MCPServer
from pearl.mcp.tools import TOOL_DEFINITIONS

logger = structlog.get_logger(__name__)

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

    async def _asgi_handler(scope, receive, send):
        if scope["type"] == "lifespan":
            async with session_manager.run():
                await receive()  # lifespan.startup
                await send({"type": "lifespan.startup.complete"})
                await receive()  # lifespan.shutdown
                await send({"type": "lifespan.shutdown.complete"})
            return
        if scope["type"] == "http":
            # Prefer user resolved by AuthMiddleware (set on scope["state"])
            state = scope.get("state")
            user = getattr(state, "user", None) if state is not None else None

            # Fallback: validate Bearer token directly (for standalone / test usage)
            if user is None:
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()
                if auth.startswith("Bearer "):
                    from pearl.api.middleware.auth import _decode_jwt
                    try:
                        payload = _decode_jwt(auth[7:])
                        user = {"sub": payload.get("sub", ""), "roles": payload.get("roles", []), "scopes": payload.get("scopes", [])}
                    except ValueError:
                        user = {}
                else:
                    user = {}

            roles = user.get("roles", [])
            scopes = user.get("scopes", [])
            sub = user.get("sub", "anonymous")
            authorized = (
                sub not in ("anonymous", "")
                and (
                    "mcp" in scopes
                    or "*" in scopes
                    or "service_account" in roles
                    or "admin" in roles
                    or "operator" in roles
                )
            )
            if not authorized:
                body = json.dumps({"error": "Unauthorized", "detail": "Valid Bearer token required for MCP access"}).encode()
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await session_manager.handle_request(scope, receive, send)

    _asgi_handler.session_manager = session_manager  # type: ignore[attr-defined]
    return _asgi_handler
