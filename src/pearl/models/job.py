"""Pydantic model for JobStatus entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import ErrorDetail, Reference
from pearl.models.enums import JobStatus as JobStatusEnum
from pearl.models.enums import JobType


class JobStatusModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    job_id: str = Field(..., pattern=r"^job_[A-Za-z0-9_-]+$")
    status: JobStatusEnum
    job_type: JobType
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime
    trace_id: str = Field(..., min_length=8, max_length=128)
    result_refs: list[Reference] | None = None
    errors: list[ErrorDetail] | None = None
