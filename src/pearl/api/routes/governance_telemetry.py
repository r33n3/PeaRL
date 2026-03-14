"""Governance telemetry push endpoints — receive audit + cost data from clients."""

import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.governance_telemetry_repo import (
    ClientAuditEventRepository,
    ClientCostEntryRepository,
)
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id


def _sign_audit_event(event_dict: dict) -> str:
    """Return HMAC-SHA256 hex digest over canonical JSON of the event fields."""
    canonical = json.dumps(event_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(
        settings.audit_hmac_key.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()

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


@router.get("/projects/{project_id}/audit-events")
async def list_audit_events(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List client audit events for a project (newest first)."""
    await _ensure_project_exists(project_id, db)
    repo = ClientAuditEventRepository(db)
    rows = await repo.list_by_project(project_id)
    return [
        {
            "event_id": r.event_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "event_type": r.event_type,
            "action": r.action,
            "decision": r.decision,
            "reason": r.reason,
            "tool_name": r.tool_name,
            "source": r.source,
            "signature": r.signature,
        }
        for r in rows
    ]


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
        event_id = generate_id("cae_")
        timestamp_dt = datetime.fromisoformat(evt.timestamp)
        # Fields used for HMAC signature (canonical subset — no mutable DB fields)
        signable = {
            "event_id": event_id,
            "project_id": project_id,
            "timestamp": timestamp_dt.isoformat(),  # normalized — must match verify endpoint
            "event_type": evt.event_type,
            "action": evt.action,
            "decision": evt.decision,
        }
        rows.append({
            "event_id": event_id,
            "project_id": project_id,
            "timestamp": timestamp_dt,
            "event_type": evt.event_type,
            "action": evt.action,
            "decision": evt.decision,
            "reason": evt.reason,
            "tool_name": evt.tool_name,
            "details": evt.details,
            "source": evt.source,
            "signature": _sign_audit_event(signable),
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


@router.get("/projects/{project_id}/audit-events/{event_id}/verify")
async def verify_audit_event(
    project_id: str,
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify the HMAC signature of a stored audit event (ACoP §9.1 immutable log check)."""
    repo = ClientAuditEventRepository(db)
    row = await repo.get_by_id("event_id", event_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("Audit event", event_id)

    if not row.signature:
        return {
            "event_id": event_id,
            "valid": None,
            "reason": "no_signature — event predates ACoP audit signing",
        }

    signable = {
        "event_id": row.event_id,
        "project_id": row.project_id,
        "timestamp": row.timestamp.isoformat(),
        "event_type": row.event_type,
        "action": row.action,
        "decision": row.decision,
    }
    expected = _sign_audit_event(signable)
    valid = hmac.compare_digest(expected, row.signature)

    return {
        "event_id": event_id,
        "valid": valid,
        "reason": "signature_match" if valid else "signature_mismatch — possible tampering",
    }
