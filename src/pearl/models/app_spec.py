"""Pydantic model for ApplicationSpec entity."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity
from pearl.models.enums import BusinessCriticality, ExternalExposure, RiskLevel


class AppIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{2,100}$")
    owner_team: str
    business_criticality: BusinessCriticality
    external_exposure: ExternalExposure
    ai_enabled: bool


class ArchComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: str
    criticality: RiskLevel | None = None


class TrustBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    from_: str | None = Field(None, alias="from")
    to: str | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Architecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    components: list[ArchComponent]
    trust_boundaries: list[TrustBoundary] | None = None


class DataClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    sensitivity: str  # public, internal, confidential, restricted


class DataSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classifications: list[DataClassification] | None = None
    prohibited_in_model_context: list[str] | None = None


class ApplicationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    kind: Literal["PearlApplicationSpec"]
    application: AppIdentity
    architecture: Architecture
    data: DataSection | None = None
    iam: dict[str, Any] | None = None
    network: dict[str, Any] | None = None
    responsible_ai: dict[str, Any] | None = None
    autonomous_coding: dict[str, Any] | None = None
    controls: dict[str, Any] | None = None
    tests: dict[str, Any] | None = None
    approvals: dict[str, Any] | None = None
    integrity: Integrity | None = None
