"""Fairness governance repositories."""

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.fairness import (
    AuditEventRow,
    ContextContractRow,
    ContextPackRow,
    ContextReceiptRow,
    EvidencePackageRow,
    FairnessCaseRow,
    FairnessExceptionRow,
    FairnessRequirementsSpecRow,
    MonitoringSignalRow,
)
from pearl.repositories.base import BaseRepository


class FairnessCaseRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FairnessCaseRow)

    async def get(self, fc_id: str) -> FairnessCaseRow | None:
        return await self.get_by_id("fc_id", fc_id)

    async def get_by_project(self, project_id: str) -> FairnessCaseRow | None:
        rows = await self.list_by_field("project_id", project_id)
        return rows[0] if rows else None

    async def list_by_project(self, project_id: str) -> list[FairnessCaseRow]:
        return await self.list_by_field("project_id", project_id)


class FairnessRequirementsSpecRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FairnessRequirementsSpecRow)

    async def get(self, frs_id: str) -> FairnessRequirementsSpecRow | None:
        return await self.get_by_id("frs_id", frs_id)

    async def get_by_project(self, project_id: str) -> FairnessRequirementsSpecRow | None:
        rows = await self.list_by_field("project_id", project_id)
        return rows[0] if rows else None


class EvidencePackageRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EvidencePackageRow)

    async def get(self, evidence_id: str) -> EvidencePackageRow | None:
        return await self.get_by_id("evidence_id", evidence_id)

    async def get_by_project_and_env(
        self, project_id: str, environment: str
    ) -> list[EvidencePackageRow]:
        stmt = select(EvidencePackageRow).where(
            and_(
                EvidencePackageRow.project_id == project_id,
                EvidencePackageRow.environment == environment,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project(self, project_id: str) -> list[EvidencePackageRow]:
        return await self.list_by_field("project_id", project_id)


class FairnessExceptionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FairnessExceptionRow)

    async def get(self, exception_id: str) -> FairnessExceptionRow | None:
        return await self.get_by_id("exception_id", exception_id)

    async def get_active_by_project(self, project_id: str) -> list[FairnessExceptionRow]:
        stmt = select(FairnessExceptionRow).where(
            and_(
                FairnessExceptionRow.project_id == project_id,
                FairnessExceptionRow.status == "active",
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MonitoringSignalRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, MonitoringSignalRow)

    async def get(self, signal_id: str) -> MonitoringSignalRow | None:
        return await self.get_by_id("signal_id", signal_id)

    async def list_by_project_and_type(
        self, project_id: str, signal_type: str
    ) -> list[MonitoringSignalRow]:
        stmt = select(MonitoringSignalRow).where(
            and_(
                MonitoringSignalRow.project_id == project_id,
                MonitoringSignalRow.signal_type == signal_type,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_type(
        self, project_id: str, signal_type: str
    ) -> MonitoringSignalRow | None:
        stmt = (
            select(MonitoringSignalRow)
            .where(
                and_(
                    MonitoringSignalRow.project_id == project_id,
                    MonitoringSignalRow.signal_type == signal_type,
                )
            )
            .order_by(MonitoringSignalRow.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ContextContractRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ContextContractRow)

    async def get(self, cc_id: str) -> ContextContractRow | None:
        return await self.get_by_id("cc_id", cc_id)


class ContextPackRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ContextPackRow)

    async def get(self, cp_id: str) -> ContextPackRow | None:
        return await self.get_by_id("cp_id", cp_id)


class ContextReceiptRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ContextReceiptRow)

    async def get(self, cr_id: str) -> ContextReceiptRow | None:
        return await self.get_by_id("cr_id", cr_id)

    async def get_by_commit(self, project_id: str, commit_hash: str) -> ContextReceiptRow | None:
        stmt = select(ContextReceiptRow).where(
            and_(
                ContextReceiptRow.project_id == project_id,
                ContextReceiptRow.commit_hash == commit_hash,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AuditEventRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AuditEventRow)

    async def list_by_resource(self, resource_id: str) -> list[AuditEventRow]:
        return await self.list_by_field("resource_id", resource_id)

    async def list_by_actor(self, actor: str) -> list[AuditEventRow]:
        return await self.list_by_field("actor", actor)

    async def list_since(self, since: datetime) -> list[AuditEventRow]:
        stmt = select(AuditEventRow).where(AuditEventRow.timestamp >= since)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def append(self, **kwargs) -> AuditEventRow:
        return await self.create(**kwargs)
