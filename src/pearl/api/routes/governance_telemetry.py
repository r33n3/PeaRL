"""Governance telemetry push endpoints — receive audit + cost data from clients."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.governance_telemetry_repo import (
    ClientAuditEventRepository,
    ClientCostEntryRepository,
)
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Governance Telemetry"])


# --- Request models ---


class AuditEventPush(BaseModel):
    timestamp: str
    event_type: str
    action: str
    decision: str
    reason: str = ""
    tool_name: str = ""
    details: dict | None = None
    source: str = "pearl_dev"


class CostEntryPush(BaseModel):
    timestamp: str
    environment: str
    workflow: str
    model: str
    cost_usd: float
    duration_ms: int | None = None
    num_turns: int = 0
    tools_called: list[str] | None = None
    tool_count: int = 0
    success: bool = True
    session_id: str | None = None


class AuditBatchPushRequest(BaseModel):
    events: list[AuditEventPush] = Field(default_factory=list, max_length=500)


class CostBatchPushRequest(BaseModel):
    entries: list[CostEntryPush] = Field(default_factory=list, max_length=500)


# --- Helpers ---


async def _ensure_project_exists(project_id: str, db: AsyncSession):
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)
    return row


# --- Routes ---


@router.post("/projects/{project_id}/audit-events", status_code=201)
async def push_audit_events(
    project_id: str,
    body: AuditBatchPushRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Receive a batch of audit events from a pearl-dev client."""
    await _ensure_project_exists(project_id, db)

    repo = ClientAuditEventRepository(db)
    rows = []
    for evt in body.events:
        rows.append({
            "event_id": generate_id("cae_"),
            "project_id": project_id,
            "timestamp": datetime.fromisoformat(evt.timestamp),
            "event_type": evt.event_type,
            "action": evt.action,
            "decision": evt.decision,
            "reason": evt.reason,
            "tool_name": evt.tool_name,
            "details": evt.details,
            "source": evt.source,
        })

    created = await repo.bulk_create(rows)
    await db.commit()
    return {"received": len(body.events), "created": created}


@router.post("/projects/{project_id}/governance-costs", status_code=201)
async def push_governance_costs(
    project_id: str,
    body: CostBatchPushRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Receive a batch of cost ledger entries from a pearl-dev client."""
    await _ensure_project_exists(project_id, db)

    repo = ClientCostEntryRepository(db)
    rows = []
    for entry in body.entries:
        rows.append({
            "entry_id": generate_id("cce_"),
            "project_id": project_id,
            "timestamp": datetime.fromisoformat(entry.timestamp),
            "environment": entry.environment,
            "workflow": entry.workflow,
            "model": entry.model,
            "cost_usd": entry.cost_usd,
            "duration_ms": entry.duration_ms,
            "num_turns": entry.num_turns,
            "tools_called": entry.tools_called,
            "tool_count": entry.tool_count,
            "success": entry.success,
            "session_id": entry.session_id,
        })

    created = await repo.bulk_create(rows)
    await db.commit()
    return {"received": len(body.entries), "created": created}
