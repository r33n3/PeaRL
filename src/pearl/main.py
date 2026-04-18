"""FastAPI application factory and lifespan management."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.config import settings
from pearl.logging_config import configure_logging

# Configure logging at import time
_json_logs = os.environ.get("PEARL_LOCAL", "0") != "1"
configure_logging(log_level=settings.log_level, json_output=_json_logs)

logger = logging.getLogger(__name__)


async def _seed_bootstrap_admin(session: AsyncSession) -> None:
    """Create the bootstrap admin user + API key if they don't exist (idempotent)."""
    import hashlib
    import secrets

    from sqlalchemy import select

    from pearl.db.models.user import ApiKeyRow, UserRow

    ADMIN_USER_ID = "usr_bootstrap_admin"
    ADMIN_EMAIL = "admin@pearl.dev"
    ADMIN_PASSWORD = "PeaRL-admin-2026"
    ADMIN_API_KEY_RAW = "pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"
    ADMIN_KEY_ID = "key_bootstrap_admin"

    existing = (await session.execute(
        select(UserRow).where(UserRow.user_id == ADMIN_USER_ID)
    )).scalar_one_or_none()

    if not existing:
        salt = secrets.token_bytes(16)
        h = hashlib.scrypt(ADMIN_PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1)  # nosec GH-32 — scrypt is a strong KDF, CodeQL false positive
        hashed_pw = f"{salt.hex()}:{h.hex()}"

        session.add(UserRow(
            user_id=ADMIN_USER_ID,
            email=ADMIN_EMAIL,
            display_name="PeaRL Admin",
            hashed_password=hashed_pw,
            roles=["admin", "reviewer", "operator", "viewer"],
            org_id="org_default",
            is_active=True,
        ))
        await session.flush()  # persist user before FK reference

        import hmac as _hmac
        _hmac_secret = (settings.api_key_hmac_secret or settings.jwt_secret).encode()
        key_hash = _hmac.new(_hmac_secret, ADMIN_API_KEY_RAW.encode(), hashlib.sha256).hexdigest()
        session.add(ApiKeyRow(
            key_id=ADMIN_KEY_ID,
            user_id=ADMIN_USER_ID,
            key_hash=key_hash,
            name="Bootstrap admin key",
            scopes=[],
            is_active=True,
        ))
        logger.info("Seeded bootstrap admin user (admin@pearl.dev)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown resources."""
    db_url = settings.effective_database_url
    engine_kwargs: dict = {"echo": False}

    # SQLite does not support pool_size / max_overflow
    if "sqlite" not in db_url:
        engine_kwargs.update(pool_size=10, max_overflow=20)

    engine = create_async_engine(db_url, **engine_kwargs)

    # Auto-create tables (SQLite for local dev; PostgreSQL for compose dev stack)
    from pearl.db.base import Base
    import pearl.db.models  # noqa: F401 — register all ORM models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB tables created/verified (%s)", "sqlite" if "sqlite" in db_url else "postgresql")

    # Seed default promotion gates (idempotent)
    from pearl.services.promotion.default_gates import seed_default_gates, seed_demo_data

    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as seed_session:
        created = await seed_default_gates(seed_session)
        await seed_demo_data(seed_session)
        await _seed_bootstrap_admin(seed_session)
        await seed_session.commit()
        if created:
            logger.info("Seeded %d default promotion gates", created)

    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Startup: Redis connection (optional in local mode)
    try:
        import redis.asyncio as aioredis
        app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.warning("Redis not available, some features will be disabled")
        app.state.redis = None

    # Start background scheduler
    from pearl.workers.scheduler import run_scheduler
    scheduler_task = asyncio.create_task(run_scheduler(app))

    logger.info("PeaRL API started (db=%s)", "sqlite" if "sqlite" in db_url else "postgresql")
    yield

    # Shutdown
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    if app.state.redis:
        await app.state.redis.close()
    await engine.dispose()
    logger.info("PeaRL API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    _expose = settings.effective_expose_openapi
    app = FastAPI(
        title="PeaRL API",
        version="1.1.0",
        description="API-first risk orchestration platform for autonomous coding and secure/responsible delivery.",
        lifespan=lifespan,
        openapi_url="/openapi.json" if _expose else None,
        docs_url="/docs" if _expose else None,
        redoc_url="/redoc" if _expose else None,
    )

    # CORS middleware for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-API-Key", "X-Request-ID"],
    )

    # Add middleware (order matters: last added = first executed)
    from pearl.api.middleware.trace_id import TraceIdMiddleware
    from pearl.api.middleware.auth import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TraceIdMiddleware)

    # Register error handlers
    from pearl.errors.handlers import register_exception_handlers
    register_exception_handlers(app)

    # Rate limiting
    from pearl.api.middleware.rate_limit import setup_rate_limiter
    setup_rate_limiter(app)

    # Prometheus metrics (internal endpoint)
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=True,
            should_respect_env_var=False,
            excluded_handlers=["/api/v1/health.*", "/metrics"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        logger.debug("prometheus-fastapi-instrumentator not installed, /metrics disabled")

    # Import and mount routers
    from pearl.api.router import api_router
    app.include_router(api_router)

    # Mount MCP streamable HTTP transport
    from pearl.mcp.http_server import build_mcp_asgi_app
    mcp_asgi = build_mcp_asgi_app(
        api_base_url=getattr(settings, "effective_public_api_url", "http://localhost:8081/api/v1"),
        api_key=None,
    )
    app.mount("/mcp", app=mcp_asgi)

    return app


app = create_app()
