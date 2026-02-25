"""Integration endpoint and sync log DB models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class IntegrationEndpointRow(Base, TimestampMixin):
    """A configured external integration endpoint."""

    __tablename__ = "integration_endpoints"

    endpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(100), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    auth_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    project_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    labels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class IntegrationSyncLogRow(Base, TimestampMixin):
    """Log entry for an integration sync operation."""

    __tablename__ = "integration_sync_logs"

    log_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("integration_endpoints.endpoint_id"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # "pull" or "push"
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # "success", "partial", "failed"
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
