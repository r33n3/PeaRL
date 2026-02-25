"""Pydantic models for fairness governance (merged from FEU concepts)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import (
    AttestationStatus,
    Environment,
    EvidenceType,
    ExceptionStatus,
    FairnessCriticality,
    GateMode,
    RiskTier,
)


class FairnessCase(BaseModel):
    """Fairness Case (FC): risk analysis and fairness principles for a project."""

    model_config = ConfigDict(extra="forbid")

    fc_id: str = Field(..., pattern=r"^fc_[A-Za-z0-9_-]+$")
    project_id: str
    risk_tier: RiskTier
    fairness_criticality: FairnessCriticality
    system_description: str | None = None
    stakeholders: list[str] | None = None
    fairness_principles: list[str] | None = None
    recourse_model: str | None = None
    case_data: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FairnessRequirement(BaseModel):
    """Single fairness requirement within an FRS."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(..., pattern=r"^fr_[A-Za-z0-9_-]+$")
    statement: str
    requirement_type: str = Field(..., pattern=r"^(prohibit|require|threshold)$")
    enforcement_points: list[Environment] | None = None
    metric_refs: list[str] | None = None
    gate_mode_per_env: dict[str, GateMode] | None = None
    threshold_value: float | None = None
    threshold_metric: str | None = None


class FairnessRequirementsSpec(BaseModel):
    """Fairness Requirements Spec (FRS): collection of fairness requirements."""

    model_config = ConfigDict(extra="forbid")

    frs_id: str = Field(..., pattern=r"^frs_[A-Za-z0-9_-]+$")
    project_id: str
    requirements: list[FairnessRequirement] = Field(..., min_length=1)
    version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Attestation(BaseModel):
    """Signed evidence record."""

    model_config = ConfigDict(extra="forbid")

    attestation_id: str = Field(..., pattern=r"^att_[A-Za-z0-9_-]+$")
    signed_by: str
    signed_at: datetime | None = None
    status: AttestationStatus = AttestationStatus.UNSIGNED
    signature_ref: str | None = None


class EvidencePackage(BaseModel):
    """Fairness Evidence (FE): CI eval reports, runtime samples, attestation."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(..., pattern=r"^fe_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    evidence_type: EvidenceType
    summary: str | None = None
    evidence_data: dict | None = None
    attestation: Attestation | None = None
    attestation_status: AttestationStatus = AttestationStatus.UNSIGNED
    freshness_days: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


class FairnessException(BaseModel):
    """Fairness Exception Record (FER): temporary exception with compensating controls."""

    model_config = ConfigDict(extra="forbid")

    exception_id: str = Field(..., pattern=r"^fer_[A-Za-z0-9_-]+$")
    project_id: str
    requirement_id: str | None = None
    rationale: str
    compensating_controls: list[str] | None = None
    status: ExceptionStatus = ExceptionStatus.PENDING
    approved_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class MonitoringSignal(BaseModel):
    """Runtime fairness signal (drift, policy violations, stereotype leakage)."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(..., pattern=r"^sig_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    signal_type: str
    value: float
    threshold: float | None = None
    metadata: dict | None = None
    recorded_at: datetime | None = None


class ContextContract(BaseModel):
    """Context Contract (CC): what context agents must consume."""

    model_config = ConfigDict(extra="forbid")

    cc_id: str = Field(..., pattern=r"^cc_[A-Za-z0-9_-]+$")
    project_id: str | None = None
    required_artifacts: list[str]
    gate_mode_per_env: dict[str, GateMode] | None = None
    description: str | None = None
    created_at: datetime | None = None


class ContextPack(BaseModel):
    """Context Pack (CP): bundled artifacts for agents."""

    model_config = ConfigDict(extra="forbid")

    cp_id: str = Field(..., pattern=r"^cp_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    pack_data: dict
    artifact_hashes: dict[str, str] | None = None
    created_at: datetime | None = None


class ContextReceipt(BaseModel):
    """Context Receipt (CR): proof agent consumed fairness context."""

    model_config = ConfigDict(extra="forbid")

    cr_id: str = Field(..., pattern=r"^cr_[A-Za-z0-9_-]+$")
    project_id: str
    commit_hash: str | None = None
    agent_id: str | None = None
    tool_calls: list[str] | None = None
    artifact_hashes: dict[str, str] | None = None
    consumed_at: datetime | None = None
