"""Pydantic models for PeaRL common definitions (common-defs.schema.json)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import HashAlgorithm, ReferenceKind


class Integrity(BaseModel):
    """Integrity hash for signed/verified artifacts."""

    model_config = ConfigDict(extra="forbid")

    signed: bool
    hash: str | None = Field(None, min_length=16)
    hash_alg: HashAlgorithm | None = None
    signer: str | None = None
    signature_ref: str | None = None
    compiled_at: datetime | None = None


class TraceabilityRef(BaseModel):
    """Traceability reference linking to source artifacts."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(..., min_length=8, max_length=128)
    source_refs: list[str] | None = None


class Reference(BaseModel):
    """Reference to a related resource or artifact."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    kind: ReferenceKind
    summary: str | None = None
    uri: str | None = None


class ErrorDetail(BaseModel):
    """Error detail in API responses."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | list[Any] | str | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error response matching error-response.schema.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.1"
    error: ErrorDetail
