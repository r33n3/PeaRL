"""Org Environment Config repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org_env_config import OrgEnvironmentConfigRow
from pearl.repositories.base import BaseRepository


class OrgEnvironmentConfigRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, OrgEnvironmentConfigRow)

    async def get(self, config_id: str) -> OrgEnvironmentConfigRow | None:
        return await self.get_by_id("config_id", config_id)

    async def get_by_org(self, org_id: str) -> OrgEnvironmentConfigRow | None:
        stmt = select(OrgEnvironmentConfigRow).where(
            OrgEnvironmentConfigRow.org_id == org_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self, config_id: str, org_id: str, stages: list
    ) -> OrgEnvironmentConfigRow:
        existing = await self.get_by_org(org_id)
        if existing:
            existing.stages = stages
            return existing
        row = OrgEnvironmentConfigRow(
            config_id=config_id,
            org_id=org_id,
            stages=stages,
        )
        self.session.add(row)
        return row
