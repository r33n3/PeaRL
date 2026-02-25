"""Base repository with common CRUD operations."""

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository:
    """Generic async repository for SQLAlchemy models."""

    def __init__(self, session: AsyncSession, model_class: type[T]):
        self.session = session
        self.model_class = model_class

    async def get_by_id(self, pk_field: str, pk_value: str) -> T | None:
        """Get a single record by primary key."""
        stmt = select(self.model_class).where(
            getattr(self.model_class, pk_field) == pk_value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs: Any) -> T:
        """Create and persist a new record."""
        row = self.model_class(**kwargs)
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, row: T, **kwargs: Any) -> T:
        """Update an existing record."""
        for key, value in kwargs.items():
            setattr(row, key, value)
        await self.session.flush()
        return row

    async def list_by_field(self, field: str, value: Any) -> list[T]:
        """List records matching a field value."""
        stmt = select(self.model_class).where(
            getattr(self.model_class, field) == value
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
