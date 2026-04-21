"""Integration tests for the MCP HTTP transport endpoint.

These tests exercise the MCP ASGI app built by ``build_mcp_asgi_app``.

The ``StreamableHTTPSessionManager`` inside that app requires its ``run()``
context to be active before any HTTP request arrives.  Our custom ASGI app
responds to ``lifespan.startup`` / ``lifespan.shutdown`` events to manage
that lifecycle.  The fixture below drives those events manually before
issuing real HTTP requests.
"""

import asyncio
import contextlib
import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient

logger = logging.getLogger(__name__)

def _service_token() -> str:
    """Generate a valid service JWT for MCP auth in tests."""
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone
    from pearl.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "litellm-mcp-client",
        "roles": ["service_account"],
        "scopes": ["mcp"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "type": "access",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


# ---------------------------------------------------------------------------
# Lifespan helper
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _lifespan_context(asgi_app):
    """Drive the ASGI lifespan startup, yield, then drive shutdown."""
    msg_queue: asyncio.Queue = asyncio.Queue()
    send_queue: asyncio.Queue = asyncio.Queue()

    await msg_queue.put({"type": "lifespan.startup"})

    async def receive():
        return await msg_queue.get()

    async def send(msg):
        await send_queue.put(msg)

    async def run_lifespan():
        await asgi_app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)

    task = asyncio.create_task(run_lifespan())

    msg = await asyncio.wait_for(send_queue.get(), timeout=5.0)
    assert msg["type"] == "lifespan.startup.complete", f"Unexpected lifespan msg: {msg}"

    try:
        yield
    finally:
        await msg_queue.put({"type": "lifespan.shutdown"})
        try:
            shutdown_msg = await asyncio.wait_for(send_queue.get(), timeout=5.0)
            assert shutdown_msg["type"] == "lifespan.shutdown.complete", f"Unexpected shutdown msg: {shutdown_msg}"
        except asyncio.TimeoutError:
            logger.warning("MCP ASGI lifespan shutdown timed out — session manager may not have cleaned up")
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_initialize():
    """POST / with initialize returns protocolVersion and serverInfo."""
    from pearl.mcp.http_server import build_mcp_asgi_app

    mcp_asgi = build_mcp_asgi_app(api_base_url="http://localhost:8080", api_key=None)

    async with _lifespan_context(mcp_asgi):
        async with AsyncClient(
            transport=ASGITransport(app=mcp_asgi),
            base_url="http://test",
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {_service_token()}"},
        ) as ac:
            r = await ac.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "0.1"},
                    },
                },
            )

    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data, f"No result in response: {data}"
    assert data["result"]["serverInfo"]["name"] == "pearl-api"
    assert "protocolVersion" in data["result"]


@pytest.mark.asyncio
async def test_mcp_list_tools():
    """tools/list returns all PeaRL tool definitions."""
    from pearl.mcp.http_server import build_mcp_asgi_app
    from pearl.mcp.tools import TOOL_DEFINITIONS

    mcp_asgi = build_mcp_asgi_app(api_base_url="http://localhost:8080", api_key=None)

    async with _lifespan_context(mcp_asgi):
        async with AsyncClient(
            transport=ASGITransport(app=mcp_asgi),
            base_url="http://test",
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {_service_token()}"},
        ) as ac:
            r = await ac.post(
                "/",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )

    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data, f"No result in response: {data}"
    tools = data["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected_names = {t["name"] for t in TOOL_DEFINITIONS}
    assert expected_names == tool_names, f"Missing tools: {expected_names - tool_names}"


@pytest.mark.asyncio
async def test_mcp_call_unknown_tool():
    """tools/call with unknown tool name returns error content, not a crash."""
    from pearl.mcp.http_server import build_mcp_asgi_app

    mcp_asgi = build_mcp_asgi_app(api_base_url="http://localhost:8080", api_key=None)

    async with _lifespan_context(mcp_asgi):
        async with AsyncClient(
            transport=ASGITransport(app=mcp_asgi),
            base_url="http://test",
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {_service_token()}"},
        ) as ac:
            r = await ac.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "nonexistent_tool", "arguments": {}},
                },
            )

    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data, f"No result in response: {data}"
    content = data["result"]["content"]
    assert len(content) > 0
    assert content[0]["type"] == "text"
    payload = json.loads(content[0]["text"])
    assert "error" in payload


@pytest.mark.asyncio
async def test_mcp_path_requires_auth(app):
    """GET /mcp without a Bearer token returns 401 (auth is enforced on /mcp).

    Uses the full PeaRL test app so that the AuthMiddleware is exercised.
    The MCP ASGI handler enforces Bearer token auth — unauthenticated requests
    must be rejected with 401.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        r = await ac.get("/mcp/")
    assert r.status_code == 401, (
        f"Expected 401 for unauthenticated /mcp/, got {r.status_code}: {r.text}"
    )
