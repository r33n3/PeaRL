"""ExceptionRecord table."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ExceptionRecordRow(Base, TimestampMixin):
    __tablename__ = "exception_records"

    exception_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(String(5000), nullable=False)
    compensating_controls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[list | None] = mapped_column(JSON, nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_cadence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
