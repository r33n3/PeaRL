"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.db.base import Base
# Import all models to register with Base.metadata
import pearl.db.models  # noqa: F401


@pytest.fixture
async def db_engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default promotion gates (mirrors main.py lifespan)
    from pearl.services.promotion.default_gates import seed_default_gates

    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as seed_session:
        await seed_default_gates(seed_session)
        await seed_session.commit()

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Create a test database session."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def app(db_engine):
    """Create a test application instance with in-memory DB."""
    from pearl.main import create_app

    _app = create_app()
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    _app.state.db_engine = db_engine
    _app.state.db_session_factory = session_factory
    _app.state.redis = None
    return _app


@pytest.fixture
async def client(app):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
