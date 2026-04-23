"""Trace ID middleware for request/response propagation."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pearl.logging_config import bind_request_context, clear_request_context


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Extract X-Trace-Id from request or generate one; bind to structlog context."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("x-trace-id") or f"trc_{uuid.uuid4().hex[:16]}"
        request.state.trace_id = trace_id
        bind_request_context(trace_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers["X-Trace-Id"] = trace_id
        return response
