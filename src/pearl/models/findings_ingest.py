"""Pydantic models for findings ingestion request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import TrustLabel
from pearl.models.finding import Finding


class SourceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str
    source_system: str
    connector_version: str | None = None
    received_at: datetime
    trust_label: TrustLabel


class IngestOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalize_on_ingest: bool | None = False
    strict_validation: bool | None = True
    quarantine_on_error: bool | None = True


class FindingsIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    source_batch: SourceBatch
    findings: list[Finding] = Field(..., min_length=1)
    options: IngestOptions | None = None


class FindingsIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    batch_id: str
    accepted_count: int
    quarantined_count: int
    normalized_count: int | None = None
    job_id: str | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)
    timestamp: datetime
