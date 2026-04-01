"""Workload repository — CRUD for WorkloadRow."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.workload import WorkloadRow
from pearl.repositories.base import BaseRepository

_INACTIVE_THRESHOLD = timedelta(minutes=5)


class WorkloadRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkloadRow)

    async def get(self, workload_id: str) -> WorkloadRow | None:
        return await self.get_by_id("workload_id", workload_id)

    async def get_by_svid(self, svid: str) -> WorkloadRow | None:
        stmt = select(WorkloadRow).where(WorkloadRow.svid == svid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[WorkloadRow]:
        """Return active workloads, auto-marking stale ones (>5 min no heartbeat) as inactive."""
        now = datetime.now(timezone.utc)
        cutoff = now - _INACTIVE_THRESHOLD

        stmt = select(WorkloadRow).where(WorkloadRow.status == "active")
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())

        active = []
        for row in rows:
            last_seen = row.last_seen_at
            # Ensure timezone-aware comparison
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if last_seen < cutoff:
                # On-read auto-deactivation: stale workload → inactive
                row.status = "inactive"
                await self.session.flush()
            else:
                active.append(row)
        return active

    async def list_all(self) -> list[WorkloadRow]:
        stmt = select(WorkloadRow)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> WorkloadRow:
        return await super().create(**kwargs)

    async def update_heartbeat(self, row: WorkloadRow) -> WorkloadRow:
        return await self.update(row, last_seen_at=datetime.now(timezone.utc))

    async def deactivate(self, row: WorkloadRow) -> WorkloadRow:
        return await self.update(row, status="inactive")

    async def count_active(self) -> int:
        """Count currently active workloads (excludes stale ones by delegating to list_active)."""
        active = await self.list_active()
        return len(active)
