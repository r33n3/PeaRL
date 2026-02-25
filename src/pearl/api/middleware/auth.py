"""JWT Bearer and API key authentication middleware."""

import hashlib
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pearl.config import settings

logger = logging.getLogger(__name__)

# Paths that do not require authentication
_PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/jwks.json",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _decode_jwt(token: str) -> dict:
    from jose import JWTError, jwt

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        raise ValueError(f"Invalid token: {exc}") from exc


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract and validate Bearer token or X-API-Key; attach user info to request.state."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip auth for public endpoints
        if path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            request.state.user = {"sub": "anonymous", "roles": [], "scopes": ["*"]}
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        api_key_header = request.headers.get("x-api-key", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_info = await self._validate_jwt(token)
        elif api_key_header:
            user_info = await self._validate_api_key(api_key_header, request)
        else:
            # No auth provided — set anonymous; individual routes enforce auth as needed
            user_info = {"sub": "anonymous", "roles": [], "scopes": []}

        request.state.user = user_info
        return await call_next(request)

    async def _validate_jwt(self, token: str) -> dict:
        try:
            payload = _decode_jwt(token)
        except ValueError:
            return {"sub": "anonymous", "roles": [], "scopes": [], "_auth_error": "invalid_token"}

        if payload.get("type") == "refresh":
            return {"sub": "anonymous", "roles": [], "scopes": [], "_auth_error": "not_access_token"}

        return {
            "sub": payload.get("sub", ""),
            "roles": payload.get("roles", []),
            "scopes": payload.get("scopes", ["*"]),
            "email": payload.get("email", ""),
        }

    async def _validate_api_key(self, raw_key: str, request: Request) -> dict:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        session_factory = getattr(request.app.state, "db_session_factory", None)
        if not session_factory:
            return {"sub": "anonymous", "roles": [], "scopes": []}

        try:
            from datetime import datetime, timezone

            from pearl.repositories.user_repo import ApiKeyRepository, UserRepository

            async with session_factory() as session:
                key_repo = ApiKeyRepository(session)
                api_key = await key_repo.get_by_hash(key_hash)

                if not api_key or not api_key.is_active:
                    return {"sub": "anonymous", "roles": [], "scopes": []}

                if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                    return {"sub": "anonymous", "roles": [], "scopes": []}

                api_key.last_used_at = datetime.now(timezone.utc)
                await session.commit()

                user_repo = UserRepository(session)
                user = await user_repo.get(api_key.user_id)
                if not user or not user.is_active:
                    return {"sub": "anonymous", "roles": [], "scopes": []}

                return {
                    "sub": user.user_id,
                    "roles": user.roles,
                    "scopes": api_key.scopes,
                    "email": user.email,
                }
        except Exception as exc:
            logger.warning("API key validation error: %s", exc)
            return {"sub": "anonymous", "roles": [], "scopes": []}
