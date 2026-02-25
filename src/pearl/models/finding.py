"""Pydantic model for Finding entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import TraceabilityRef
from pearl.models.enums import (
    Confidence,
    Environment,
    Exploitability,
    FindingCategory,
    FindingStatus,
    RiskLevel,
    ToolType,
    TrustLabel,
)


class FindingSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    tool_type: ToolType
    connector_id: str | None = None
    trust_label: TrustLabel
    raw_record_ref: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    finding_id: str = Field(..., pattern=r"^find_[A-Za-z0-9_-]+$")
    source: FindingSource
    project_id: str
    environment: Environment
    category: FindingCategory
    severity: RiskLevel
    confidence: Confidence | None = None
    title: str
    description: str | None = None
    affected_components: list[str] | None = None
    control_refs: list[str] | None = None
    exploitability: Exploitability | None = None
    detected_at: datetime
    normalized: bool | None = None
    traceability: TraceabilityRef | None = None
    # Scoring + status fields (Step 33)
    cvss_score: float | None = Field(None, ge=0.0, le=10.0)
    cwe_ids: list[str] | None = None
    cve_id: str | None = None
    status: FindingStatus = FindingStatus.OPEN
    fix_available: bool | None = None
    score: float | None = None
    compliance_refs: dict | None = None
    verdict: dict | None = None
    rai_eval_type: str | None = None
