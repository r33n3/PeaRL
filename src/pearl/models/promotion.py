"""Pydantic models for promotion gates and environment progression."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import (
    Environment,
    GateEvaluationStatus,
    GateRuleResult,
    GateRuleType,
    PromotionRequestStatus,
)

# Environment key pattern: lowercase, starts with letter, allows digits/hyphens/underscores
_ENV_KEY_PATTERN = r"^[a-z][a-z0-9_-]{0,49}$"


class PipelineStage(BaseModel):
    """A single stage in a promotion pipeline."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., pattern=_ENV_KEY_PATTERN)
    label: str
    description: str | None = None
    order: int


class PromotionPipeline(BaseModel):
    """An ordered named list of promotion stages for an org (or project)."""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str = Field(..., pattern=r"^pipe_[A-Za-z0-9_-]+$")
    project_id: str | None = None
    name: str
    description: str | None = None
    stages: list[PipelineStage] = Field(..., min_length=1)
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GateRuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., pattern=r"^rule_[A-Za-z0-9_-]+$")
    rule_type: GateRuleType
    description: str
    required: bool = True
    threshold: float | None = None
    parameters: dict | None = None
    ai_only: bool = False


class PromotionGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(..., pattern=r"^gate_[A-Za-z0-9_-]+$")
    # Relaxed from Environment enum to plain string to support custom pipeline stages
    source_environment: str = Field(..., pattern=_ENV_KEY_PATTERN)
    target_environment: str = Field(..., pattern=_ENV_KEY_PATTERN)
    project_id: str | None = None
    rules: list[GateRuleDefinition] = Field(..., min_length=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RuleEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_type: GateRuleType
    result: GateRuleResult
    message: str
    details: dict | None = None
    exception_id: str | None = None


class PromotionEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(..., pattern=r"^eval_[A-Za-z0-9_-]+$")
    project_id: str
    gate_id: str
    # Plain strings to support custom pipeline stage keys
    source_environment: str
    target_environment: str
    status: GateEvaluationStatus
    rule_results: list[RuleEvaluationResult]
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    total_count: int = 0
    progress_pct: float = 0.0
    blockers: list[str] | None = None
    evaluated_at: datetime | None = None
    trace_id: str | None = None


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., pattern=r"^promreq_[A-Za-z0-9_-]+$")
    project_id: str
    evaluation_id: str
    approval_request_id: str | None = None
    source_environment: str
    target_environment: str
    status: PromotionRequestStatus
    requested_by: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None


class PromotionHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_id: str = Field(..., pattern=r"^promhist_[A-Za-z0-9_-]+$")
    project_id: str
    source_environment: str
    target_environment: str
    evaluation_id: str
    promoted_by: str
    promoted_at: datetime
    details: dict | None = None


class PromotionReadiness(BaseModel):
    """Lightweight summary included in compiled context packages."""

    model_config = ConfigDict(extra="forbid")

    current_environment: str
    next_environment: str | None = None
    status: GateEvaluationStatus
    progress_pct: float = 0.0
    passed_count: int = 0
    total_count: int = 0
    blockers: list[str] | None = None
    last_evaluated_at: datetime | None = None
