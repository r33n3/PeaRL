"""Repository for FactoryRunSummaryRow — idempotent upsert on frun_id."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.factory_run_summary import FactoryRunSummaryRow
from pearl.repositories.base import BaseRepository


class FactoryRunSummaryRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FactoryRunSummaryRow)

    async def get(self, frun_id: str) -> FactoryRunSummaryRow | None:
        return await self.get_by_id("frun_id", frun_id)

    async def get_by_task_packet(self, task_packet_id: str) -> FactoryRunSummaryRow | None:
        """Return the first run summary linked to a task packet."""
        stmt = (
            select(FactoryRunSummaryRow)
            .where(FactoryRunSummaryRow.task_packet_id == task_packet_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> list[FactoryRunSummaryRow]:
        return await self.list_by_field("project_id", project_id)

    async def upsert(self, data: dict) -> FactoryRunSummaryRow:
        """Idempotent upsert on frun_id.

        Uses PostgreSQL ``ON CONFLICT DO UPDATE`` when available (production).
        Falls back to a manual get-or-create path for SQLite (local/test).
        Sets ``updated_at`` on every upsert.  Returns the live row after flush.
        """
        data = dict(data)  # defensive copy
        data.setdefault("updated_at", datetime.now(timezone.utc))
        frun_id = data["frun_id"]

        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            set_cols = {
                k: v
                for k, v in data.items()
                if k not in ("frun_id", "created_at")
            }
            stmt = (
                pg_insert(FactoryRunSummaryRow)
                .values(**data)
                .on_conflict_do_update(
                    index_elements=["frun_id"],
                    set_=set_cols,
                )
            )
            await self.session.execute(stmt)
            await self.session.flush()
        except Exception:
            # SQLite (local dev / tests) — fall back to manual upsert
            existing = await self.get(frun_id)
            if existing is None:
                await self.create(**data)
            else:
                update_data = {k: v for k, v in data.items() if k not in ("frun_id", "created_at")}
                await self.update(existing, **update_data)

        return await self.get(frun_id)
