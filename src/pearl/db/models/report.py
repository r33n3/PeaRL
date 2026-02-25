"""Report table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ReportRow(Base, TimestampMixin):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
