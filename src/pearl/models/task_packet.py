"""Pydantic model for TaskPacket entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Reference
from pearl.models.enums import Environment, TaskType


class ContextBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tokens_hint: int | None = Field(None, ge=256)
    deep_fetch_required: bool | None = None


class TaskPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    task_packet_id: str = Field(..., pattern=r"^tp_[A-Za-z0-9_-]+$")
    project_id: str
    environment: Environment
    task_type: TaskType
    task_summary: str = Field(..., min_length=1, max_length=3000)
    affected_components: list[str] | None = None
    relevant_controls: list[str] | None = None
    relevant_rai_requirements: list[str] | None = None
    allowed_actions: list[str]
    blocked_actions: list[str]
    required_tests: list[str] | None = None
    approval_triggers: list[str] | None = None
    evidence_required: list[str] | None = None
    reassessment_triggers: list[str] | None = None
    references: list[Reference] | None = None
    trace_id: str = Field(..., min_length=8, max_length=128)
    generated_at: datetime
    context_budget: ContextBudget | None = None
