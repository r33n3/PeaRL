"""Audit event routes."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.repositories.fairness_repo import AuditEventRepository

router = APIRouter(tags=["Audit"])


@router.get("/audit/events", status_code=200)
async def list_audit_events(
    resource_id: str | None = None,
    action_type: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = AuditEventRepository(db)

    if resource_id:
        events = await repo.list_by_resource(resource_id)
    elif actor:
        events = await repo.list_by_actor(actor)
    elif since:
        events = await repo.list_since(datetime.fromisoformat(since))
    else:
        # Return empty for now (no list-all to avoid unbounded queries)
        events = []

    # Filter by action_type if provided
    if action_type and events:
        events = [e for e in events if e.action_type == action_type]

    return [
        {
            "event_id": e.event_id,
            "resource_id": e.resource_id,
            "action_type": e.action_type,
            "actor": e.actor,
            "details": e.details,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]


@router.get("/audit/events/resource/{resource_id}", status_code=200)
async def get_events_by_resource(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = AuditEventRepository(db)
    events = await repo.list_by_resource(resource_id)
    return [
        {
            "event_id": e.event_id,
            "action_type": e.action_type,
            "actor": e.actor,
            "details": e.details,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]
