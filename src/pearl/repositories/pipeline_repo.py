"""Repository for PromotionPipelineRow."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.promotion import PromotionPipelineRow
from pearl.repositories.base import BaseRepository


class PromotionPipelineRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PromotionPipelineRow)

    async def get(self, pipeline_id: str) -> PromotionPipelineRow | None:
        return await self.get_by_id("pipeline_id", pipeline_id)

    async def get_default(self) -> PromotionPipelineRow | None:
        """Return the current org-level default pipeline."""
        stmt = select(PromotionPipelineRow).where(
            PromotionPipelineRow.is_default.is_(True),
            PromotionPipelineRow.project_id.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PromotionPipelineRow]:
        """List all pipelines ordered by creation date."""
        stmt = select(PromotionPipelineRow).order_by(PromotionPipelineRow.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_default(self, pipeline_id: str) -> None:
        """Set pipeline as default, clearing any previous default."""
        # Clear all defaults first
        await self.session.execute(
            update(PromotionPipelineRow).values(is_default=False)
        )
        # Set the new default
        pipeline = await self.get(pipeline_id)
        if pipeline:
            pipeline.is_default = True
            await self.session.flush()

    async def delete(self, pipeline_id: str) -> None:
        """Delete a pipeline by ID."""
        pipeline = await self.get(pipeline_id)
        if pipeline:
            await self.session.delete(pipeline)
            await self.session.flush()
