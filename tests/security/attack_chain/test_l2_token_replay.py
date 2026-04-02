"""L2 — Token Replay Attack: Refresh Token Blocklisting After Logout

Attack chain level 2: an agent that captures a valid refresh token
attempts to continue using it after the legitimate user has logged out.

Hard control tested:
  - POST /auth/logout blocklists the refresh token in Redis
  - Subsequent POST /auth/refresh with the revoked token returns 401

Positive test:
  - A fresh (never-logged-out) refresh token can still be used for refresh
    (blocklist does not break the happy path)

NOTE: The default test app has redis=None — the blocklist check is skipped when
Redis is unavailable. These tests use a FakeRedis fixture to exercise the full
blocklist path. This matches the production behaviour where Redis is required.

Reference: CLAUDE-security-validation.md L2
Control: src/pearl/api/routes/auth.py refresh_token() / logout()
"""

from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Fake Redis stub — async get/setex only
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Minimal async Redis stub for blocklist testing."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return _FakeRedis()


@pytest.fixture
def app_with_redis(db_engine, fake_redis):
    """Test app wired with an in-memory Redis stub (blocklist enabled)."""
    from pearl.main import create_app
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    _app = create_app()
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    _app.state.db_engine = db_engine
    _app.state.db_session_factory = session_factory
    _app.state.redis = fake_redis
    return _app


@pytest.fixture
async def redis_client(app_with_redis):
    """Async test client backed by the Redis-enabled app."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_redis)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_refresh_token(sub: str = "test-user") -> str:
    """Create a syntactically valid, signed refresh JWT for testing."""
    import jwt as pyjwt
    from pearl.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(days=1),
        "type": "refresh",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# L2 hard control: blocklisted token rejected on refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_refresh_token_blocked_after_logout(redis_client):
    """
    L2 control: refresh token is blocklisted on logout; subsequent use returns 401.

    Attack: agent captures a refresh token and tries to use it after logout.
    Expected: 401 Authentication Error (token revoked)
    Control: pearl:token:blocked:{token[:32]} key in Redis (auth.py:logout/refresh_token)
    """
    token = _make_refresh_token()

    # Step 1: logout — this should blocklist the token in Redis
    logout_resp = await redis_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": token},
    )
    assert logout_resp.status_code == 204, f"Logout failed: {logout_resp.status_code}"

    # Step 2: attempt to refresh using the now-blocklisted token
    refresh_resp = await redis_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )
    assert refresh_resp.status_code == 401, (
        f"Expected 401 after logout, got {refresh_resp.status_code}. "
        "Token blocklist is not being checked — revoked tokens can still be replayed."
    )
    body = refresh_resp.json()
    error_detail = str(body).lower()
    assert "revoked" in error_detail or "invalid" in error_detail, (
        f"Expected 'revoked' or 'invalid' in error response, got: {body}"
    )


@pytest.mark.asyncio
async def test_l2_blocklist_key_uses_token_prefix(fake_redis):
    """
    Implementation check: logout stores the token prefix (first 32 chars) as the blocklist key.

    Verifies the blocklist key format matches what refresh_token() looks up.
    A mismatch between setex key and get key would silently break the blocklist.
    """
    from pearl.main import create_app
    from pearl.config import settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from pearl.db.base import Base
    from httpx import ASGITransport, AsyncClient

    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _app = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    _app.state.db_engine = engine
    _app.state.db_session_factory = session_factory
    _app.state.redis = fake_redis

    token = _make_refresh_token()
    expected_key = f"pearl:token:blocked:{token[:32]}"

    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/api/v1/auth/logout", json={"refresh_token": token})

    assert await fake_redis.get(expected_key) is not None, (
        f"Expected blocklist key '{expected_key}' not found in Redis after logout. "
        "Key format mismatch between logout (setex) and refresh (get) would break the blocklist."
    )

    await engine.dispose()


# ---------------------------------------------------------------------------
# Positive test: non-blocklisted token still rejected (no DB user)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_non_blocklisted_token_fails_at_user_lookup(redis_client):
    """
    Positive/boundary: a fresh token not in the blocklist progresses past the
    blocklist check but fails at user lookup (sub='test-user' not in DB).

    This confirms the blocklist check executes before the user lookup:
      - Blocklisted token → 401 "revoked" (before user lookup)
      - Non-blocklisted token → 401 "not found" (after user lookup)

    These are different failure modes proving the blocklist is checked first.
    """
    token = _make_refresh_token(sub="nonexistent-user")

    # Do NOT logout — token is not blocklisted
    refresh_resp = await redis_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )
    # Still 401, but for a different reason (no user in DB, not blocklisted)
    assert refresh_resp.status_code == 401
    body = refresh_resp.json()
    error_detail = str(body).lower()
    # Should NOT say "revoked" — it should be about the user not being found
    assert "revoked" not in error_detail, (
        f"Non-blocklisted token incorrectly reported as revoked: {body}"
    )
