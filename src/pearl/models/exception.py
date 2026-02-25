"""Pydantic model for ExceptionRecord entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import Environment, ExceptionStatus


class ExceptionScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment | None = None
    components: list[str] | None = None
    controls: list[str] | None = None


class ExceptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    exception_id: str = Field(..., pattern=r"^exc_[A-Za-z0-9_-]+$")
    project_id: str
    scope: ExceptionScope | None = None
    requested_by: str
    rationale: str
    compensating_controls: list[str] | None = None
    approved_by: list[str] | None = None
    status: ExceptionStatus
    start_at: datetime | None = None
    expires_at: datetime | None = None
    review_cadence_days: int | None = Field(None, ge=1)
    trace_id: str = Field(..., min_length=8, max_length=128)
