"""Pydantic model for EnvironmentProfile entity."""

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity
from pearl.models.enums import (
    ApprovalLevel,
    AutonomyMode,
    DeliveryStage,
    Environment,
    RiskLevel,
)


class EnvironmentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    profile_id: str = Field(..., pattern=r"^envp_[A-Za-z0-9_-]+$")
    environment: Environment
    delivery_stage: DeliveryStage
    risk_level: RiskLevel
    autonomy_mode: AutonomyMode
    allowed_capabilities: list[str] | None = None
    blocked_capabilities: list[str] | None = None
    approval_level: ApprovalLevel | None = None
    integrity: Integrity | None = None
