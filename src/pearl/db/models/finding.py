"""Finding and FindingBatch tables."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class FindingRow(Base, TimestampMixin):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[dict] = mapped_column(JSON, nullable=False)
    full_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
    # Scoring + status fields (Step 33)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cwe_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cve_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    fix_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    compliance_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rai_eval_type: Mapped[str | None] = mapped_column(String(100), nullable=True)


class FindingBatchRow(Base, TimestampMixin):
    __tablename__ = "finding_batches"

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(200), nullable=False)
    trust_label: Mapped[str] = mapped_column(String(50), nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
