"""Business Unit repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.business_unit import BusinessUnitRow
from pearl.repositories.base import BaseRepository


class BusinessUnitRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, BusinessUnitRow)

    async def get(self, bu_id: str) -> BusinessUnitRow | None:
        return await self.get_by_id("bu_id", bu_id)

    async def get_by_org(self, org_id: str) -> list[BusinessUnitRow]:
        stmt = select(BusinessUnitRow).where(BusinessUnitRow.org_id == org_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, org_id: str, name: str) -> BusinessUnitRow | None:
        stmt = select(BusinessUnitRow).where(
            BusinessUnitRow.org_id == org_id,
            BusinessUnitRow.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        bu_id: str,
        org_id: str,
        name: str,
        description: str | None = None,
        framework_selections: list | None = None,
        additional_guardrails: dict | None = None,
    ) -> BusinessUnitRow:
        row = BusinessUnitRow(
            bu_id=bu_id,
            org_id=org_id,
            name=name,
            description=description,
            framework_selections=framework_selections or [],
            additional_guardrails=additional_guardrails or {},
        )
        self.session.add(row)
        return row

    async def update(self, row: BusinessUnitRow, **kwargs) -> BusinessUnitRow:
        for k, v in kwargs.items():
            if v is not None or k in ("description",):
                setattr(row, k, v)
        return row

    async def delete(self, bu_id: str) -> None:
        row = await self.get(bu_id)
        if row:
            await self.session.delete(row)
