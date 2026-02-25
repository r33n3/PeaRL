"""Fairness governance tables (merged from FEU concepts)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class FairnessCaseRow(Base, TimestampMixin):
    __tablename__ = "fairness_cases"

    fc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    fairness_criticality: Mapped[str] = mapped_column(String(20), nullable=False)
    case_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FairnessRequirementsSpecRow(Base, TimestampMixin):
    __tablename__ = "fairness_requirements_specs"

    frs_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    requirements: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)


class EvidencePackageRow(Base, TimestampMixin):
    __tablename__ = "evidence_packages"

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attestation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unsigned")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FairnessExceptionRow(Base, TimestampMixin):
    __tablename__ = "fairness_exceptions"

    exception_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    requirement_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    compensating_controls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MonitoringSignalRow(Base, TimestampMixin):
    __tablename__ = "monitoring_signals"

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContextContractRow(Base, TimestampMixin):
    __tablename__ = "context_contracts"

    cc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=True, index=True
    )
    required_artifacts: Mapped[list] = mapped_column(JSON, nullable=False)
    gate_mode_per_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ContextPackRow(Base, TimestampMixin):
    __tablename__ = "context_packs"

    cp_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    pack_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifact_hashes: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ContextReceiptRow(Base, TimestampMixin):
    __tablename__ = "context_receipts"

    cr_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    artifact_hashes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
