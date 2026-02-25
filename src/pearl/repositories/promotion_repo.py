"""Promotion gate, evaluation, and history repositories."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.promotion import (
    PromotionEvaluationRow,
    PromotionGateRow,
    PromotionHistoryRow,
)
from pearl.repositories.base import BaseRepository


class PromotionGateRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PromotionGateRow)

    async def get(self, gate_id: str) -> PromotionGateRow | None:
        return await self.get_by_id("gate_id", gate_id)

    async def get_for_transition(
        self, source_env: str, target_env: str, project_id: str | None = None
    ) -> PromotionGateRow | None:
        """Get gate for a transition. Project-specific override falls back to org default."""
        if project_id:
            stmt = select(PromotionGateRow).where(
                and_(
                    PromotionGateRow.source_environment == source_env,
                    PromotionGateRow.target_environment == target_env,
                    PromotionGateRow.project_id == project_id,
                )
            )
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return row

        # Fallback to org default (project_id is NULL)
        stmt = select(PromotionGateRow).where(
            and_(
                PromotionGateRow.source_environment == source_env,
                PromotionGateRow.target_environment == target_env,
                PromotionGateRow.project_id.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_defaults(self) -> list[PromotionGateRow]:
        """List all org-level default gates."""
        stmt = select(PromotionGateRow).where(PromotionGateRow.project_id.is_(None))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PromotionEvaluationRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PromotionEvaluationRow)

    async def get(self, evaluation_id: str) -> PromotionEvaluationRow | None:
        return await self.get_by_id("evaluation_id", evaluation_id)

    async def get_latest_by_project(self, project_id: str) -> PromotionEvaluationRow | None:
        stmt = (
            select(PromotionEvaluationRow)
            .where(PromotionEvaluationRow.project_id == project_id)
            .order_by(PromotionEvaluationRow.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class PromotionHistoryRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PromotionHistoryRow)

    async def list_by_project(self, project_id: str) -> list[PromotionHistoryRow]:
        return await self.list_by_field("project_id", project_id)
