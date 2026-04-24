"""Rate limiting middleware using slowapi."""

import structlog
import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from pearl.config import settings

logger = structlog.get_logger(__name__)

# HTTP methods considered "writes"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Inject X-RateLimit-* headers on every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        response = await call_next(request)

        # Limit value depends on method
        if request.method in _WRITE_METHODS:
            limit = settings.rate_limit_writes_per_minute
        else:
            limit = settings.rate_limit_reads_per_minute

        response.headers["X-RateLimit-Limit"] = str(limit)

        # Copy remaining from slowapi if present
        remaining = response.headers.get("RateLimit-Remaining")
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = remaining

        # Next minute boundary as unix timestamp
        response.headers["X-RateLimit-Reset"] = str(int((time.time() // 60 + 1) * 60))

        return response


def setup_rate_limiter(app) -> None:
    """Attach slowapi limiter to the FastAPI app."""
    if not settings.rate_limit_enabled:
        return

    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address

        def get_rate_limit_key(request: Request) -> str:
            """Use user_id for authenticated users, IP for anonymous."""
            user = getattr(request.state, "user", {})
            sub = user.get("sub", "")
            if sub and sub not in ("anonymous", ""):
                return f"user:{sub}"
            return get_remote_address(request)

        limiter = Limiter(
            key_func=get_rate_limit_key,
            default_limits=[],
            storage_uri=settings.redis_url,
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(RateLimitHeadersMiddleware)
        logger.info("Rate limiter configured (writes=%d/min, reads=%d/min)",
                    settings.rate_limit_writes_per_minute,
                    settings.rate_limit_reads_per_minute)
    except ImportError:
        logger.warning(
            "slowapi is not installed — rate limiting is DISABLED. "
            "Install it with: pip install slowapi"
        )
