"""Pydantic models for ReportRequest and ReportResponse entities."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import ReportFormat, ReportStatus, ReportType


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    report_type: ReportType
    format: ReportFormat
    filters: dict[str, Any] | None = None
    include_references: bool | None = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    report_id: str = Field(..., pattern=r"^rpt_[A-Za-z0-9_-]+$")
    report_type: str
    status: ReportStatus
    format: ReportFormat
    content: dict[str, Any] | str | None = None
    artifact_ref: str | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)
    generated_at: datetime | None = None
