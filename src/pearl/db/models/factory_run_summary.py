"""Factory run summary — one aggregated row per WTK factory run."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class FactoryRunSummaryRow(Base, TimestampMixin):
    """Aggregated summary for a single WTK factory run.

    The ``frun_id`` is the session_id supplied by WTK agents when pushing
    cost entries to ``client_cost_entries``.  The upsert in the repository
    is idempotent so two triggers (workload deregister + task packet complete)
    can both fire without creating duplicates.
    """

    __tablename__ = "factory_run_summaries"

    frun_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    task_packet_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    goal_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    svid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    models_used: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tools_called: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anomaly_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promotion_env: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
