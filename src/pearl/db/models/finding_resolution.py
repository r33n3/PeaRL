"""FindingResolution table — evidence and approval trail for resolved findings."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class FindingResolutionRow(Base, TimestampMixin):
    __tablename__ = "finding_resolutions"

    resolution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    finding_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("findings.finding_id"),
        nullable=False,
        index=True,
        unique=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    resolved_by: Mapped[str] = mapped_column(String(500), nullable=False)
    # "human" | "rescan"
    approval_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    # "pending" | "approved" | "rejected" | "auto_approved"
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    evidence_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    test_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
