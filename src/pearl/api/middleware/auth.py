"""JWT Bearer authentication middleware (stubbed for dev)."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract Bearer token and attach user info to request state.

    Currently stubbed - allows all requests through.
    Full JWT validation will be implemented in Step 11.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Stub: extract token but don't validate
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            request.state.user = {"sub": "dev-user", "scopes": ["*"]}
        else:
            request.state.user = {"sub": "anonymous", "scopes": ["*"]}

        return await call_next(request)
