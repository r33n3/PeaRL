"""FastAPI application factory and lifespan management."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown resources."""
    db_url = settings.effective_database_url
    engine_kwargs: dict = {"echo": False}

    # SQLite does not support pool_size / max_overflow
    if "sqlite" not in db_url:
        engine_kwargs.update(pool_size=10, max_overflow=20)

    engine = create_async_engine(db_url, **engine_kwargs)

    # Auto-create tables for SQLite (local dev — no Alembic migrations)
    if "sqlite" in db_url:
        from pearl.db.base import Base
        import pearl.db.models  # noqa: F401 — register all ORM models

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLite tables created (local mode)")

        # Seed default promotion gates (idempotent)
        from pearl.services.promotion.default_gates import seed_default_gates

        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as seed_session:
            created = await seed_default_gates(seed_session)
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

    logger.info("PeaRL API started (db=%s)", "sqlite" if "sqlite" in db_url else "postgresql")
    yield

    # Shutdown
    if app.state.redis:
        await app.state.redis.close()
    await engine.dispose()
    logger.info("PeaRL API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PeaRL API",
        version="1.1.0",
        description="API-first risk orchestration platform for autonomous coding and secure/responsible delivery.",
        lifespan=lifespan,
    )

    # CORS middleware for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative dev port
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add middleware (order matters: last added = first executed)
    from pearl.api.middleware.trace_id import TraceIdMiddleware
    from pearl.api.middleware.auth import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TraceIdMiddleware)

    # Register error handlers
    from pearl.errors.handlers import register_exception_handlers
    register_exception_handlers(app)

    # Import and mount routers
    from pearl.api.router import api_router
    app.include_router(api_router)

    return app


app = create_app()
