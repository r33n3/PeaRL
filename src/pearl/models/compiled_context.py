"""Pydantic model for CompiledContextPackage entity."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity, Reference, TraceabilityRef
from pearl.models.enums import (
    AutonomyMode,
    DeliveryStage,
    Environment,
    RemediationEligibility,
)


class CompiledFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_baseline_id: str
    app_spec_id: str
    environment_profile_id: str
    remediation_overlay_id: str | None = None


class PackageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str = Field(..., pattern=r"^pkg_[A-Za-z0-9_-]+$")
    compiled_from: CompiledFrom
    integrity: Integrity
    compiler_version: str | None = None
    merge_precedence_version: str | None = None


class ProjectIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    app_id: str | None = None
    environment: Environment
    delivery_stage: DeliveryStage | None = None
    ai_enabled: bool


class AutonomyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: AutonomyMode
    allowed_actions: list[str]
    blocked_actions: list[str]
    approval_required_for: list[str] | None = None


class SecurityRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_controls: list[str]
    prohibited_patterns: list[str] | None = None


class Transparency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_disclosure_required: bool | None = None
    model_provenance_logging_required: bool | None = None
    explanation_metadata_required: str | None = None  # none, basic, enhanced


class Fairness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_required: bool | None = None
    monitoring_required: bool | None = None


class Oversight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    human_review_required_for: list[str] | None = None


class ResponsibleAiRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transparency: Transparency | None = None
    fairness: Fairness | None = None
    oversight: Oversight | None = None


class IamRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    least_privilege_required: bool | None = None


class NetworkRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outbound_allowlist: list[str] | None = None
    public_egress_forbidden: bool | None = None


class DataHandlingRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prohibited_in_model_context: list[str] | None = None


class ToolAndModelConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_tool_classes: list[str] | None = None
    forbidden_tool_classes: list[str] | None = None
    allowed_model_tiers: list[str] | None = None
    forbidden_model_tiers: list[str] | None = None


class RequiredTests(BaseModel):
    model_config = ConfigDict(extra="forbid")
    security: list[str] | None = None
    rai: list[str] | None = None
    functional: list[str] | None = None


class ApprovalCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint_id: str
    trigger: str
    required_roles: list[str] | None = None
    environment: Environment | None = None


class ChangeReassessmentTriggers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    architecture_delta: list[str] | None = None


class RemediationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: str
    eligibility: RemediationEligibility


class AutonomousRemediationEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: RemediationEligibility | None = None
    rules: list[RemediationRule] | None = None


class CompiledContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    kind: Literal["PearlCompiledContextPackage"]
    package_metadata: PackageMetadata
    project_identity: ProjectIdentity
    environment_profile: dict | None = None
    autonomy_policy: AutonomyPolicy
    security_requirements: SecurityRequirements
    responsible_ai_requirements: ResponsibleAiRequirements | None = None
    iam_requirements: IamRequirements | None = None
    network_requirements: NetworkRequirements | None = None
    data_handling_requirements: DataHandlingRequirements | None = None
    tool_and_model_constraints: ToolAndModelConstraints | None = None
    required_tests: RequiredTests | None = None
    approval_checkpoints: list[ApprovalCheckpoint] | None = None
    evidence_requirements: list[str] | None = None
    change_reassessment_triggers: ChangeReassessmentTriggers | None = None
    autonomous_remediation_eligibility: AutonomousRemediationEligibility | None = None
    exceptions: list[str] | None = None
    promotion_readiness: dict | None = None
    fairness_requirements: dict | None = None
    traceability: TraceabilityRef | None = None
    references: list[Reference] | None = None
