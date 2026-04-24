"""Webhook subscription management API."""

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, RequireOperator, RequireViewer
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = structlog.get_logger(__name__)


@router.post("/subscriptions", status_code=201)
async def create_subscription(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user=RequireOperator,
):
    url = body.get("url", "").strip()
    secret = body.get("secret", "").strip()
    event_types = body.get("event_types") or []
    if not url or not secret:
        raise ValidationError("url and secret are required")
    repo = WebhookSubscriptionRepository(db)
    sub_id = await repo.create(url=url, secret=secret, event_types=event_types)
    await db.commit()
    subs = await repo.list_active()
    row = next((s for s in subs if s.subscription_id == sub_id), None)
    return {
        "subscription_id": sub_id,
        "url": row.url if row else url,
        "event_types": row.event_types if row else event_types,
        "active": True,
    }


@router.get("/subscriptions", status_code=200)
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    _user=RequireViewer,
):
    repo = WebhookSubscriptionRepository(db)
    subs = await repo.list_active()
    return [
        {
            "subscription_id": s.subscription_id,
            "url": s.url,
            "event_types": s.event_types,
            "active": s.active,
        }
        for s in subs
    ]


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def deactivate_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    _user=RequireOperator,
):
    repo = WebhookSubscriptionRepository(db)
    subs = await repo.list_active()
    if not any(s.subscription_id == subscription_id for s in subs):
        raise NotFoundError("WebhookSubscription", subscription_id)
    await repo.deactivate(subscription_id)
    await db.commit()
    return Response(status_code=204)
