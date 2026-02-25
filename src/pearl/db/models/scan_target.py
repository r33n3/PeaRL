"""ScanTarget table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ScanTargetRow(Base, TimestampMixin):
    __tablename__ = "scan_targets"

    scan_target_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    repo_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    tool_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scan_frequency: Mapped[str] = mapped_column(String(50), nullable=False, default="daily")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    environment_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    labels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scan_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "repo_url", "tool_type", "branch",
            name="uq_scan_target_project_repo_tool_branch",
        ),
    )
