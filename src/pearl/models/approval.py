"""Pydantic models for ApprovalRequest and ApprovalDecision entities."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import (
    ApprovalDecisionValue,
    ApprovalRequestType,
    ApprovalStatus,
    Environment,
)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    approval_request_id: str = Field(..., pattern=r"^appr_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    request_type: ApprovalRequestType
    trigger: str
    requested_by: str
    required_roles: list[str] | None = None
    artifact_refs: list[str] | None = None
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    approval_request_id: str = Field(..., pattern=r"^appr_[A-Za-z0-9_-]+$")
    decision: ApprovalDecisionValue
    decided_by: str
    decider_role: str
    reason: str | None = None
    conditions: list[str] | None = None
    decided_at: datetime
    trace_id: str = Field(..., min_length=8, max_length=128)


class ApprovalComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(..., pattern=r"^acmt_[A-Za-z0-9_-]+$")
    approval_request_id: str = Field(..., pattern=r"^appr_[A-Za-z0-9_-]+$")
    author: str
    author_role: str
    content: str = Field(..., min_length=1, max_length=10000)
    comment_type: str = Field(..., pattern=r"^(question|evidence|note|decision_note)$")
    attachments: dict | None = None


class ApprovalCommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str
    author_role: str
    content: str = Field(..., min_length=1, max_length=10000)
    comment_type: str = Field(..., pattern=r"^(question|evidence|note|decision_note)$")
    attachments: dict | None = None
    set_needs_info: bool = False  # Optionally change status to needs_info
