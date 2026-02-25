"""Client-pushed governance telemetry — audit events and cost entries."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ClientAuditEventRow(Base, TimestampMixin):
    """Audit events pushed from pearl-dev clients."""

    __tablename__ = "client_audit_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ClientCostEntryRow(Base, TimestampMixin):
    """Cost ledger entries pushed from pearl-dev clients."""

    __tablename__ = "client_cost_entries"

    entry_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tools_called: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
