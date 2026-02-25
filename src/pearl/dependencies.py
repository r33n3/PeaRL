"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request


async def get_db(request: Request) -> AsyncGenerator:
    """Yield a database session from the app's session factory."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


async def get_redis(request: Request):
    """Return the Redis connection pool from app state."""
    return request.app.state.redis


def get_trace_id(request: Request) -> str:
    """Extract trace_id from request state (set by middleware)."""
    return getattr(request.state, "trace_id", "unknown")


# Type aliases for dependency injection
DBSession = Annotated[object, Depends(get_db)]
RedisConn = Annotated[object, Depends(get_redis)]
TraceId = Annotated[str, Depends(get_trace_id)]
