"""Promotion gate, evaluation, and history tables."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class PromotionGateRow(Base, TimestampMixin):
    __tablename__ = "promotion_gates"

    gate_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=True, index=True
    )
    rules: Mapped[dict] = mapped_column(JSON, nullable=False)
    approval_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")


class PromotionEvaluationRow(Base, TimestampMixin):
    __tablename__ = "promotion_evaluations"

    evaluation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    gate_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("promotion_gates.gate_id"), nullable=False
    )
    source_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_results: Mapped[dict] = mapped_column(JSON, nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    blockers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromotionHistoryRow(Base, TimestampMixin):
    __tablename__ = "promotion_history"

    history_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    source_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(50), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    promoted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PromotionPipelineRow(Base, TimestampMixin):
    """Ordered promotion pipeline — one named list of stages per org (or project)."""

    __tablename__ = "promotion_pipelines"

    pipeline_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # NULL = org-level default; non-NULL = project-specific override (future)
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSON list of PipelineStage dicts: [{key, label, description, order}, ...]
    stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
