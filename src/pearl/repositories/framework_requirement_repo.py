"""Framework Requirement repository."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.framework_requirement import FrameworkRequirementRow
from pearl.repositories.base import BaseRepository


class FrameworkRequirementRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FrameworkRequirementRow)

    async def get(self, requirement_id: str) -> FrameworkRequirementRow | None:
        return await self.get_by_id("requirement_id", requirement_id)

    async def get_by_bu(self, bu_id: str) -> list[FrameworkRequirementRow]:
        stmt = select(FrameworkRequirementRow).where(
            FrameworkRequirementRow.bu_id == bu_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_bu_and_transition(
        self, bu_id: str, source: str, target: str
    ) -> list[FrameworkRequirementRow]:
        """Return requirements that apply to a specific transition or all transitions."""
        transition = f"{source}->{target}"
        all_reqs = await self.get_by_bu(bu_id)
        return [
            r
            for r in all_reqs
            if "*" in (r.applies_to_transitions or [])
            or transition in (r.applies_to_transitions or [])
        ]

    async def create(
        self,
        requirement_id: str,
        bu_id: str,
        framework: str,
        control_id: str,
        applies_to_transitions: list,
        requirement_level: str = "mandatory",
        evidence_type: str = "attestation",
    ) -> FrameworkRequirementRow:
        row = FrameworkRequirementRow(
            requirement_id=requirement_id,
            bu_id=bu_id,
            framework=framework,
            control_id=control_id,
            applies_to_transitions=applies_to_transitions,
            requirement_level=requirement_level,
            evidence_type=evidence_type,
        )
        self.session.add(row)
        return row

    async def delete_by_bu(self, bu_id: str) -> int:
        """Delete all requirements for a BU. Returns count deleted."""
        stmt = delete(FrameworkRequirementRow).where(
            FrameworkRequirementRow.bu_id == bu_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount
