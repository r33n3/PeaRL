"""Rate limiting middleware using slowapi."""

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from pearl.config import settings

logger = logging.getLogger(__name__)

# HTTP methods considered "writes"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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
        logger.info("Rate limiter configured (writes=%d/min, reads=%d/min)",
                    settings.rate_limit_writes_per_minute,
                    settings.rate_limit_reads_per_minute)
    except ImportError:
        logger.debug("slowapi not installed, rate limiting disabled")
