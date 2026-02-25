"""Pydantic model for Project entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import TraceabilityRef
from pearl.models.enums import BusinessCriticality, ExternalExposure


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    project_id: str = Field(..., pattern=r"^proj_[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    owner_team: str = Field(..., min_length=1)
    business_criticality: BusinessCriticality
    external_exposure: ExternalExposure
    ai_enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    traceability: TraceabilityRef | None = None
