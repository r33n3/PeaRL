"""Pydantic model for OrgBaseline entity."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity


class CodingDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secure_coding_standard_required: bool | None = None
    secret_hardcoding_forbidden: bool | None = None
    dependency_pinning_required: bool | None = None


class LoggingDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_logging_required: bool | None = None
    pii_in_logs_forbidden_by_default: bool | None = None
    security_events_minimum: list[str] | None = None


class IamDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    least_privilege_required: bool | None = None
    wildcard_permissions_forbidden_by_default: bool | None = None


class NetworkDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outbound_connectivity_must_be_declared: bool | None = None
    deny_by_default_preferred: bool | None = None


class ResponsibleAiDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_use_disclosure_required_for_user_facing: bool | None = None
    model_provenance_logging_required: bool | None = None
    human_oversight_required_for_high_impact_actions: bool | None = None
    fairness_review_required_when_user_impact_is_material: bool | None = None


class TestingDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_tests_required: bool | None = None
    security_tests_baseline_required: bool | None = None
    rai_evals_required_for_ai_enabled_apps: bool | None = None


class OrgDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coding: CodingDefaults
    logging: LoggingDefaults | None = None
    iam: IamDefaults
    network: NetworkDefaults
    responsible_ai: ResponsibleAiDefaults | None = None
    testing: TestingDefaults


class OrgBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    kind: Literal["PearlOrgBaseline"]
    baseline_id: str = Field(..., pattern=r"^orgb_[A-Za-z0-9_-]+$")
    org_name: str
    defaults: OrgDefaults
    environment_defaults: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    integrity: Integrity | None = None
