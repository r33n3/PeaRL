"""Repository for Cedar policy deployment records."""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.cedar_deployment import CedarDeploymentRow
from pearl.repositories.base import BaseRepository


class CedarDeploymentRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CedarDeploymentRow)

    async def get(self, deployment_id: str) -> CedarDeploymentRow | None:
        return await self.get_by_id("deployment_id", deployment_id)

    async def get_latest_for_org(self, org_id: str) -> CedarDeploymentRow | None:
        """Return the most recent active deployment for an org.

        Used by the CloudWatch bridge to retrieve the expected bundle hash
        for drift detection (CWD-001).
        """
        stmt = (
            select(CedarDeploymentRow)
            .where(CedarDeploymentRow.org_id == org_id)
            .where(CedarDeploymentRow.status == "active")
            .order_by(desc(CedarDeploymentRow.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_hash(self, bundle_hash: str) -> CedarDeploymentRow | None:
        """Look up a deployment by its bundle hash."""
        stmt = select(CedarDeploymentRow).where(
            CedarDeploymentRow.bundle_hash == bundle_hash
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(
        self, org_id: str, limit: int = 50
    ) -> list[CedarDeploymentRow]:
        """Return deployment history for an org, newest first."""
        stmt = (
            select(CedarDeploymentRow)
            .where(CedarDeploymentRow.org_id == org_id)
            .order_by(desc(CedarDeploymentRow.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def supersede_active(self, org_id: str) -> int:
        """Mark all active deployments for org as superseded.

        Called before persisting a new active deployment so only one row
        holds status='active' per org at any time.  Returns the count of
        rows updated.
        """
        from sqlalchemy import update

        stmt = (
            update(CedarDeploymentRow)
            .where(CedarDeploymentRow.org_id == org_id)
            .where(CedarDeploymentRow.status == "active")
            .values(status="superseded")
        )
        result = await self.session.execute(stmt)
        return result.rowcount
