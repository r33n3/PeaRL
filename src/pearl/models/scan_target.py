"""Pydantic models for ScanTarget entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import (
    Environment,
    ScanFrequency,
    ScanTargetStatus,
    ToolType,
)


class ScanTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    scan_target_id: str = Field(..., pattern=r"^scnt_[A-Za-z0-9_-]+$")
    project_id: str = Field(..., pattern=r"^proj_[A-Za-z0-9_-]+$")
    repo_url: str = Field(..., min_length=1, max_length=2000)
    branch: str = Field(default="main", min_length=1, max_length=200)
    tool_type: ToolType
    scan_frequency: ScanFrequency = ScanFrequency.DAILY
    status: ScanTargetStatus = ScanTargetStatus.ACTIVE
    environment_scope: list[Environment] | None = None
    labels: dict[str, str] | None = None
    last_scanned_at: datetime | None = None
    last_scan_status: str | None = Field(None, max_length=50)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScanTargetCreate(BaseModel):
    """Request body for creating a scan target (server generates ID + timestamps)."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(..., min_length=1, max_length=2000)
    branch: str = Field(default="main", min_length=1, max_length=200)
    tool_type: ToolType
    scan_frequency: ScanFrequency = ScanFrequency.DAILY
    environment_scope: list[Environment] | None = None
    labels: dict[str, str] | None = None


class ScanTargetUpdate(BaseModel):
    """Partial update of a scan target."""

    model_config = ConfigDict(extra="forbid")

    branch: str | None = None
    scan_frequency: ScanFrequency | None = None
    status: ScanTargetStatus | None = None
    environment_scope: list[Environment] | None = None
    labels: dict[str, str] | None = None


class ScanTargetDiscovery(BaseModel):
    """Stripped-down response for tool-facing discovery endpoint."""

    model_config = ConfigDict(extra="forbid")

    scan_target_id: str
    project_id: str
    repo_url: str
    branch: str
    environment_scope: list[str] | None = None
    labels: dict[str, str] | None = None
    scan_frequency: str
    last_scanned_at: datetime | None = None
