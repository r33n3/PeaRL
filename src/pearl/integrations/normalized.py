"""Normalized data models — canonical intermediates between external tools and PeaRL."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NormalizedFinding(BaseModel):
    """Normalized finding from any external source (Snyk, Semgrep, Trivy, etc.).

    This is the canonical intermediate format. Source adapters convert external
    tool output INTO this model, and the bridge converts it INTO PeaRL's Finding.
    """

    model_config = ConfigDict(extra="forbid")

    external_id: str
    source_tool: str
    source_type: str  # "sast", "sca", "container_scan", etc.
    title: str
    description: str | None = None
    severity: str  # "critical", "high", "moderate", "low"
    confidence: str | None = None  # "high", "medium", "low"
    category: str = "security"  # "security", "responsible_ai", "governance"
    affected_components: list[str] | None = None
    cwe_ids: list[str] | None = None
    cve_id: str | None = None
    cvss_score: float | None = Field(None, ge=0.0, le=10.0)
    fix_available: bool | None = None
    detected_at: datetime
    raw_record: dict | None = None  # Original payload for traceability


class NormalizedSecurityEvent(BaseModel):
    """Security event for SIEM/log sinks."""

    model_config = ConfigDict(extra="forbid")

    event_type: str  # "finding_created", "gate_passed", "promotion_approved"
    severity: str
    timestamp: datetime
    project_id: str
    summary: str
    details: dict = Field(default_factory=dict)
    finding_ids: list[str] | None = None


class NormalizedTicket(BaseModel):
    """Ticket for Jira/GitHub Issues sinks."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    priority: str  # "critical", "high", "medium", "low"
    labels: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    project_id: str
    assignee: str | None = None


class NormalizedNotification(BaseModel):
    """Notification for Slack/Teams/email sinks."""

    model_config = ConfigDict(extra="forbid")

    channel: str | None = None
    subject: str
    body: str
    severity: str
    project_id: str
    finding_ids: list[str] | None = None
