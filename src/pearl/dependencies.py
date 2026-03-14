"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request

from pearl.errors.exceptions import AuthenticationError, AuthorizationError

# Roles authorized to make approval/exception decisions
REVIEWER_ROLES = ("security_reviewer", "security_analyst", "security_manager", "governance", "admin")


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


async def get_current_user(request: Request) -> dict:
    """Return the authenticated user dict or raise 401."""
    from pearl.config import settings

    user = getattr(request.state, "user", {})

    # Local reviewer mode: grant reviewer roles without full local_mode (dev/demo use only)
    if settings.local_reviewer_mode and (not user or user.get("sub") in ("anonymous", "")):
        return {
            "sub": "local_admin",
            "roles": list(REVIEWER_ROLES) + ["operator"],
            "scopes": ["*"],
        }
    if settings.local_mode and (not user or user.get("sub") in ("anonymous", "")):
        return {
            "sub": "local_admin",
            "roles": ["operator"],
            "scopes": ["*"],
        }

    if not user or user.get("sub") in ("anonymous", ""):
        raise AuthenticationError("Authentication required")
    if "_auth_error" in user:
        raise AuthenticationError(user["_auth_error"])
    return user


def require_role(*roles: str):
    """Return a dependency that enforces one of the given roles."""

    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(roles):
            raise AuthorizationError(f"Requires one of: {', '.join(roles)}")
        return user

    return _check


# Type aliases for dependency injection
DBSession = Annotated[object, Depends(get_db)]
RedisConn = Annotated[object, Depends(get_redis)]
TraceId = Annotated[str, Depends(get_trace_id)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
RequireAdmin = Depends(require_role("admin"))
RequireOperator = Depends(require_role("operator", "admin"))
RequireReviewer = Depends(require_role(*REVIEWER_ROLES))
