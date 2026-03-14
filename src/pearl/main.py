"""FastAPI application factory and lifespan management."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.config import settings
from pearl.logging_config import configure_logging

# Configure logging at import time
_json_logs = os.environ.get("PEARL_LOCAL", "0") != "1"
configure_logging(log_level=settings.log_level, json_output=_json_logs)

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

    # Auto-create tables (SQLite for local dev; PostgreSQL for compose dev stack)
    from pearl.db.base import Base
    import pearl.db.models  # noqa: F401 — register all ORM models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe column additions for existing DBs (create_all skips existing tables)
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE org_baselines ADD COLUMN bu_id VARCHAR(128)"))
            else:
                await conn.execute(text("ALTER TABLE org_baselines ADD COLUMN IF NOT EXISTS bu_id VARCHAR(128) REFERENCES business_units(bu_id)"))
        except Exception:
            pass  # Column already exists
        # Allow org-level integrations (project_id nullable)
        try:
            if "sqlite" not in db_url:
                await conn.execute(text("ALTER TABLE integration_endpoints ALTER COLUMN project_id DROP NOT NULL"))
        except Exception:
            pass  # Already nullable or table doesn't exist yet
        # CLAUDE.md governance verification flag
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN claude_md_verified BOOLEAN NOT NULL DEFAULT 0"))
            else:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS claude_md_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        except Exception:
            pass  # Already exists
        # Exception governance enrichment columns
        for col_sql_sqlite, col_sql_pg in [
            ("ALTER TABLE exception_records ADD COLUMN exception_type VARCHAR(20) NOT NULL DEFAULT 'exception'",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS exception_type VARCHAR(20) NOT NULL DEFAULT 'exception'"),
            ("ALTER TABLE exception_records ADD COLUMN title VARCHAR(256)",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS title VARCHAR(256)"),
            ("ALTER TABLE exception_records ADD COLUMN risk_rating VARCHAR(20)",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(20)"),
            ("ALTER TABLE exception_records ADD COLUMN remediation_plan TEXT",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS remediation_plan TEXT"),
            ("ALTER TABLE exception_records ADD COLUMN board_briefing TEXT",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS board_briefing TEXT"),
            ("ALTER TABLE exception_records ADD COLUMN finding_ids JSON",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS finding_ids JSONB"),
        ]:
            try:
                await conn.execute(text(col_sql_sqlite if "sqlite" in db_url else col_sql_pg))
            except Exception:
                pass
        # Project tags column
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN tags JSON"))
            else:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS tags JSONB"))
        except Exception:
            pass
    logger.info("DB tables created/verified (%s)", "sqlite" if "sqlite" in db_url else "postgresql")

    # Seed default promotion gates (idempotent)
    from pearl.services.promotion.default_gates import seed_default_gates, seed_demo_data

    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as seed_session:
        created = await seed_default_gates(seed_session)
        await seed_demo_data(seed_session)
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

    return app


app = create_app()
