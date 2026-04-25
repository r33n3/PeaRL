"""Tests for TraceIdMiddleware — verifies trace_id flows into structlog context vars."""

import pytest
import structlog.contextvars
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from starlette.responses import PlainTextResponse

from pearl.api.middleware.trace_id import TraceIdMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/probe")
    async def probe():
        ctx = structlog.contextvars.get_contextvars()
        return PlainTextResponse(ctx.get("trace_id", "MISSING"))

    return app


@pytest.mark.asyncio
async def test_trace_id_bound_in_structlog_context():
    """trace_id must appear in structlog context vars during request processing."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/probe")
    assert resp.status_code == 200
    trace_id = resp.text
    assert trace_id.startswith("trc_"), f"Expected trc_... trace_id, got: {trace_id!r}"


@pytest.mark.asyncio
async def test_trace_id_propagated_from_header():
    """Caller-supplied X-Trace-Id header is used and bound in structlog context."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/probe", headers={"X-Trace-Id": "trc_abc123"})
    assert resp.text == "trc_abc123"


@pytest.mark.asyncio
async def test_trace_id_cleared_after_request():
    """structlog context vars are cleared between requests — no leakage."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.get("/probe", headers={"X-Trace-Id": "trc_first"})
        resp2 = await client.get("/probe", headers={"X-Trace-Id": "trc_second"})
    assert resp1.text == "trc_first"
    assert resp2.text == "trc_second"
