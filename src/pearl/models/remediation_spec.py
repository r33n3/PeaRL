"""Pydantic model for RemediationSpec entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity, Reference
from pearl.models.enums import Confidence, Environment, RemediationEligibility, RiskLevel


class RiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_level: RiskLevel
    business_impact: RiskLevel | None = None
    confidence: Confidence


class RemediationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    remediation_spec_id: str = Field(..., pattern=r"^rs_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    finding_refs: list[str]
    risk_summary: RiskSummary
    eligibility: RemediationEligibility
    required_outcome: str
    implementation_constraints: list[str] | None = None
    required_tests: list[str] | None = None
    evidence_required: list[str] | None = None
    approval_required: bool | None = None
    approval_triggers: list[str] | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)
    generated_at: datetime
    integrity: Integrity | None = None
    references: list[Reference] | None = None
