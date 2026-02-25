"""Job table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class JobRow(Base, TimestampMixin):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    result_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
