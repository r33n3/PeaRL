"""Async SQLAlchemy engine and session creation."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.config import settings


def create_db_engine(url: str | None = None):
    """Create an async SQLAlchemy engine."""
    return create_async_engine(
        url or settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
    )


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
