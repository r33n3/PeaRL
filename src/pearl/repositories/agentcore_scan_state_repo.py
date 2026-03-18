"""Repository for AgentCore CloudWatch scan state."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.agentcore_scan_state import AgentCoreScanStateRow
from pearl.repositories.base import BaseRepository
from pearl.services.id_generator import generate_id


class AgentCoreScanStateRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AgentCoreScanStateRow)

    async def get_for_org(self, org_id: str) -> AgentCoreScanStateRow | None:
        stmt = select(AgentCoreScanStateRow).where(
            AgentCoreScanStateRow.org_id == org_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        org_id: str,
        log_watermark: datetime | None = None,
        last_scan_job_id: str | None = None,
        last_scan_findings_count: int | None = None,
        last_scan_entries_processed: int | None = None,
        baseline_call_rate: float | None = None,
    ) -> AgentCoreScanStateRow:
        """Create or update scan state for an org.

        Only the supplied keyword arguments are written — omitted fields
        are left unchanged on existing rows.
        """
        row = await self.get_for_org(org_id)
        updates: dict = {}

        if log_watermark is not None:
            updates["log_watermark"] = log_watermark
        if last_scan_job_id is not None:
            updates["last_scan_job_id"] = last_scan_job_id
        if last_scan_findings_count is not None:
            updates["last_scan_findings_count"] = last_scan_findings_count
        if last_scan_entries_processed is not None:
            updates["last_scan_entries_processed"] = last_scan_entries_processed
        if baseline_call_rate is not None:
            updates["baseline_call_rate"] = baseline_call_rate

        if row:
            return await self.update(row, **updates)

        return await self.create(
            state_id=generate_id("cws_"),
            org_id=org_id,
            **updates,
        )
