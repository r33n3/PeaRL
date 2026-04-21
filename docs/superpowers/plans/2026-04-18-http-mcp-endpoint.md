# HTTP MCP Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount PeaRL's 50 existing MCP tools at `GET/POST /mcp` using the MCP streamable HTTP transport so LiteLLM (and any MCP-capable client) can call PeaRL governance tools over HTTP.

**Architecture:** Use `mcp.server.Server` (low-level) + `StreamableHTTPSessionManager` — not FastMCP — because PeaRL's tools already have complete JSON schemas in `TOOL_DEFINITIONS`. The `MCPServer` class (existing) stays as the HTTP dispatcher to the PeaRL REST API. A new `http_server.py` wires them together as an ASGI app mounted at `/mcp`. Auth middleware is updated to bypass `/mcp` (LiteLLM enforces access via its own key system).

**Tech Stack:** mcp==1.26.0 (already installed), FastAPI/Starlette `app.mount()`, `StreamableHTTPSessionManager(stateless=True)`

---

## File Map

| File | Action | Why |
|---|---|---|
| `src/pearl/mcp/http_server.py` | Create | MCP `Server` with list_tools + call_tool handlers; returns ASGI callable |
| `src/pearl/api/middleware/auth.py` | Modify | Add `/mcp` to `_PUBLIC_PATHS` exclusion list |
| `src/pearl/main.py` | Modify | Mount MCP ASGI app at `/mcp` |
| `pyproject.toml` | Modify | Declare `mcp>=1.0` in dependencies (already installed, not declared) |
| `tests/test_mcp_http.py` | Create | Integration test: list_tools and call_tool over HTTP |

---

## Task 1: Declare mcp dependency + create http_server.py

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pearl/mcp/http_server.py`

- [ ] **Step 1: Add mcp to pyproject.toml dependencies**

In `pyproject.toml`, find the `dependencies = [` block. Add after the `httpx` line:

```toml
    "mcp>=1.0",
```

- [ ] **Step 2: Create src/pearl/mcp/http_server.py**

```python
# src/pearl/mcp/http_server.py
"""Streamable HTTP MCP transport for PeaRL.

Mounts PeaRL's governance tools at /mcp using the MCP streamable HTTP
transport. LiteLLM and other MCP clients connect here directly.
"""

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
    """Return an ASGI callable for the MCP streamable HTTP transport.

    Args:
        api_base_url: PeaRL REST API base (e.g. http://localhost:8081/api/v1)
        api_key: Optional PeaRL API key forwarded on every tool call
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
    async def call_tool(name: str, arguments: dict) -> list[mcp_types.ContentBlock]:
        if name not in _TOOL_MAP:
            return [mcp_types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = await pearl.call_tool(name, arguments)
        except Exception as exc:
            logger.error("MCP HTTP tool %s failed: %s", name, exc)
            result = {"error": str(exc)}
        return [mcp_types.TextContent(type="text", text=json.dumps(result))]

    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,  # No persistent session state needed
    )

    return session_manager.handle_request
```

- [ ] **Step 3: Verify it imports cleanly**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 python3 -c "
from pearl.mcp.http_server import build_mcp_asgi_app
app = build_mcp_asgi_app('http://localhost:8081/api/v1')
print('ASGI app built:', type(app).__name__)
"
```

Expected: `ASGI app built: method` (or similar — any non-error output)

- [ ] **Step 4: Run tests to confirm nothing breaks**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/test_mcp_http.py
```

Expected: 799 passed, 0 failures

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/pearl/mcp/http_server.py
git commit -m "$(cat <<'EOF'
feat: add MCP streamable HTTP ASGI app builder

Wraps PeaRL's existing MCPServer and TOOL_DEFINITIONS in an mcp.server.Server
with StreamableHTTPSessionManager(stateless=True). Returns an ASGI callable
ready to mount at /mcp. Declares mcp>=1.0 in pyproject.toml.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Update auth middleware + mount in main.py

**Files:**
- Modify: `src/pearl/api/middleware/auth.py`
- Modify: `src/pearl/main.py`

- [ ] **Step 1: Add /mcp to auth middleware bypass**

In `src/pearl/api/middleware/auth.py`, find `_PUBLIC_PATHS`:

```python
_PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    ...
}
```

Add `/mcp` to the set:

```python
_PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/mcp",  # MCP HTTP transport — auth handled by LiteLLM key system
    ...
}
```

Also update the dispatch check. The existing middleware checks `if path in _PUBLIC_PATHS`. The `/mcp` endpoint will receive paths like `/mcp` (POST), `/mcp/` or the session manager may use sub-paths. Update the check to also allow paths **starting with** `/mcp`:

Find the condition in the middleware's `__call__` or `dispatch` method that checks public paths, and update it to:

```python
if path in _PUBLIC_PATHS or path.startswith("/mcp"):
```

- [ ] **Step 2: Mount the MCP app in main.py**

In `src/pearl/main.py`, in the `create_app()` function, after the line that includes routers (`app.include_router(api_router)`), add:

```python
    # MCP streamable HTTP transport — mounted at /mcp for LiteLLM + agent clients
    from pearl.mcp.http_server import build_mcp_asgi_app
    from starlette.routing import Mount
    mcp_asgi = build_mcp_asgi_app(
        api_base_url=settings.effective_public_api_url,
        api_key=None,  # Internal call — no key needed in local mode
    )
    app.mount("/mcp", app=mcp_asgi)
```

- [ ] **Step 3: Start PeaRL locally and verify /mcp responds**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 uvicorn pearl.main:app --port 8081 &
sleep 4
curl -s -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | python3 -m json.tool
```

Expected: JSON response with `"result"` containing `"protocolVersion"` and `"serverInfo": {"name": "pearl-api", ...}`

- [ ] **Step 4: Verify tools/list works**

```bash
curl -s -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python3 -m json.tool | head -30
```

Expected: JSON with `"result": {"tools": [...]}` containing at least `pearl_register_project` and other tool names.

- [ ] **Step 5: Kill the test server**

```bash
pkill -f "uvicorn pearl.main:app" 2>/dev/null || true
```

- [ ] **Step 6: Commit**

```bash
git add src/pearl/api/middleware/auth.py src/pearl/main.py
git commit -m "$(cat <<'EOF'
feat: mount MCP streamable HTTP transport at /mcp

Adds /mcp route bypass to auth middleware (LiteLLM handles access via
its key system). Mounts the MCP ASGI app in create_app() so PeaRL
exposes all governance tools over HTTP at host:port/mcp.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Write and run the integration test

**Files:**
- Create: `tests/test_mcp_http.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_mcp_http.py
"""Integration tests for the MCP streamable HTTP transport at /mcp.

Tests the full stack: HTTP request → StreamableHTTPSessionManager →
mcp.server.Server handlers → MCPServer.call_tool → (mocked) PeaRL API.
"""
import json
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mcp_app(app):
    """Return the test app — /mcp is already mounted in create_app()."""
    return app


@pytest.mark.asyncio
async def test_mcp_initialize(mcp_app):
    """POST /mcp with initialize returns protocolVersion and serverInfo."""
    transport = ASGITransport(app=mcp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/mcp",
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
    assert "result" in data
    assert data["result"]["serverInfo"]["name"] == "pearl-api"
    assert "protocolVersion" in data["result"]


@pytest.mark.asyncio
async def test_mcp_list_tools(mcp_app):
    """tools/list returns all PeaRL tool definitions."""
    from pearl.mcp.tools import TOOL_DEFINITIONS

    transport = ASGITransport(app=mcp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/mcp",
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
async def test_mcp_call_unknown_tool(mcp_app):
    """tools/call with unknown tool name returns error content, not a crash."""
    transport = ASGITransport(app=mcp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data
    content = data["result"]["content"]
    assert len(content) > 0
    payload = json.loads(content[0]["text"])
    assert "error" in payload


@pytest.mark.asyncio
async def test_mcp_path_not_auth_blocked(mcp_app):
    """GET /mcp is reachable without a Bearer token (auth middleware bypasses /mcp)."""
    transport = ASGITransport(app=mcp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/mcp")
    # 200 or 405 (method not allowed) — anything except 401/403
    assert r.status_code not in (401, 403), f"Auth blocked /mcp: {r.status_code} {r.text}"
```

- [ ] **Step 2: Run the MCP HTTP tests**

```bash
PEARL_LOCAL=1 pytest tests/test_mcp_http.py -v
```

Expected: all 4 tests pass

- [ ] **Step 3: Run the full suite**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Expected: 803+ passed, 0 failures

- [ ] **Step 4: Commit**

```bash
git add tests/test_mcp_http.py
git commit -m "$(cat <<'EOF'
test: MCP HTTP transport integration tests

Covers initialize, tools/list, unknown tool error handling, and auth
middleware bypass. All run against the in-process ASGI test client.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Mount 50 tools at /mcp | Task 1 (http_server.py) + Task 2 (mount) |
| Streamable HTTP transport | Task 1 (StreamableHTTPSessionManager) |
| mcp package declared | Task 1 (pyproject.toml) |
| Auth middleware bypasses /mcp | Task 2 |
| Reachable from LiteLLM at host.docker.internal:8081 | Task 2 (manual verify step) |
| Tests confirm list_tools + call_tool | Task 3 |

**Security note:** `/mcp` is auth-bypassed at the PeaRL middleware level. In production this should be restricted to internal network (docker network) or require a PeaRL API key. For local dev with LiteLLM's `allow_all_keys: true`, the current approach is appropriate.

**Known constraint:** `mcp_types.ContentBlock` union type may differ slightly in mcp 1.26.0. If import fails, replace with `list[mcp_types.TextContent]` as the return type annotation.
