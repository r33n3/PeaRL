"""Audit event routes."""

import hashlib
import hmac as _hmac
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.dependencies import get_current_user, get_db
from pearl.repositories.fairness_repo import AuditEventRepository

router = APIRouter(tags=["Audit"])


def _verify_signature(event) -> bool:
    """Recompute HMAC for an event and compare to stored signature."""
    if not event.signature or not event.timestamp:
        return False
    # Strip tz to match canonical form used in append() — must be consistent
    ts = event.timestamp.replace(tzinfo=None)
    payload = (
        f"{event.event_id}:"
        f"{event.resource_id}:"
        f"{event.action_type}:"
        f"{event.actor or ''}:"
        f"{ts.isoformat()}"
    )
    expected = _hmac.new(
        settings.audit_hmac_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return _hmac.compare_digest(expected, event.signature)


@router.get("/audit/events", status_code=200)
async def list_audit_events(
    resource_id: str | None = None,
    action_type: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
) -> list[dict]:
    repo = AuditEventRepository(db)

    if resource_id:
        events = await repo.list_by_resource(resource_id)
    elif actor:
        events = await repo.list_by_actor(actor)
    elif since:
        events = await repo.list_since(datetime.fromisoformat(since))
    else:
        events = []

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
            "hmac_valid": _verify_signature(e),
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
