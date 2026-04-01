"""AllowanceProfile repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.allowance_profile import AllowanceProfileRow
from pearl.repositories.base import BaseRepository


class AllowanceProfileRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AllowanceProfileRow)

    async def get(self, profile_id: str) -> AllowanceProfileRow | None:
        return await self.get_by_id("profile_id", profile_id)
