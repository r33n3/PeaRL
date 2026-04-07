"""Repository for scanner_policy_store table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.scanner_policy import ScannerPolicyRow
from pearl.services.id_generator import generate_id


class ScannerPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        project_id: str,
        source: str,
        scan_id: str,
        policy_type: str,
        content: dict,
    ) -> ScannerPolicyRow:
        """Upsert by (project_id, source, policy_type) — one row per scanner per policy type."""
        stmt = select(ScannerPolicyRow).where(
            ScannerPolicyRow.project_id == project_id,
            ScannerPolicyRow.source == source,
            ScannerPolicyRow.policy_type == policy_type,
        ).limit(1)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if row:
            row.scan_id = scan_id
            row.content = content
            row.updated_at = now
        else:
            row = ScannerPolicyRow(
                id=generate_id("sps"),
                project_id=project_id,
                source=source,
                scan_id=scan_id,
                policy_type=policy_type,
                content=content,
                updated_at=now,
            )
            self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_project(
        self, project_id: str, source: str | None = None
    ) -> list[ScannerPolicyRow]:
        """Return all scanner policies for a project, optionally filtered by source."""
        stmt = select(ScannerPolicyRow).where(ScannerPolicyRow.project_id == project_id)
        if source:
            stmt = stmt.where(ScannerPolicyRow.source == source)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
