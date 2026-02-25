"""Trace ID middleware for request/response propagation."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Extract X-Trace-Id from request or generate one, attach to response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("x-trace-id") or f"trc_{uuid.uuid4().hex[:16]}"
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
