"""Repository for User and ApiKey records."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.user import ApiKeyRow, UserRow
from pearl.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, UserRow)

    async def get(self, user_id: str) -> UserRow | None:
        return await self.get_by_id("user_id", user_id)

    async def get_by_email(self, email: str) -> UserRow | None:
        stmt = select(UserRow).where(UserRow.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_last_login(self, user: UserRow) -> None:
        user.last_login = datetime.now(timezone.utc)
        await self.session.flush()


class ApiKeyRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApiKeyRow)

    async def get_by_hash(self, key_hash: str) -> ApiKeyRow | None:
        stmt = select(ApiKeyRow).where(
            ApiKeyRow.key_hash == key_hash,
            ApiKeyRow.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: str) -> list[ApiKeyRow]:
        return await self.list_by_field("user_id", user_id)

    async def revoke(self, api_key: ApiKeyRow) -> None:
        api_key.is_active = False
        await self.session.flush()
