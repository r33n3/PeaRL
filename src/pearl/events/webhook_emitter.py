"""Webhook event emission with HMAC-SHA256 signing."""

import asyncio
import hashlib
import hmac
import json
import logging
import random
from datetime import datetime, timezone

import httpx

from pearl.models.webhook import WebhookEnvelope
from pearl.services.id_generator import generate_id

from .webhook_config import WebhookSubscription, webhook_registry

logger = logging.getLogger(__name__)


class _DBSubscription:
    """Adapts WebhookSubscriptionRow to the WebhookSubscription interface expected by _deliver."""

    def __init__(self, row) -> None:
        self.url = row.url
        # Use secret_hash as the signing secret — consistent across restarts.
        # The plaintext is not stored; secret_hash is the stable per-subscriber secret.
        self.secret = row.secret_hash
        self.event_types = row.event_types or []
        self.active = row.active


def _sign_payload(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature over the raw JSON body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_envelope(
    event_type: str,
    payload: dict,
    source_system: str = "pearl-api",
) -> WebhookEnvelope:
    """Build a webhook envelope (unsigned). Signature is added per-subscriber."""
    return WebhookEnvelope(
        schema_version="1.1",
        event_type=event_type,
        event_id=generate_id("evt_"),
        occurred_at=datetime.now(timezone.utc),
        source_system=source_system,
        payload=payload,
    )


async def emit_event(
    event_type: str,
    payload: dict,
    source_system: str = "pearl-api",
    db=None,
) -> list[dict]:
    """Emit a webhook event to all matching subscribers.

    When db is provided, queries subscriptions from the database (HA-safe).
    Falls back to the in-memory registry when db=None (backward compat).
    Returns a list of delivery results (url, status, error).
    """
    if db is not None:
        from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository
        db_rows = await WebhookSubscriptionRepository(db).get_subscribers(event_type)
        subscribers = [_DBSubscription(row) for row in db_rows]
    else:
        subscribers = webhook_registry.get_subscribers(event_type)

    if not subscribers:
        return []

    envelope = build_envelope(event_type, payload, source_system)
    results = []
    for sub in subscribers:
        result = await _deliver(envelope, sub, db=db)
        results.append(result)
    return results


async def _deliver(envelope: WebhookEnvelope, sub: WebhookSubscription, db=None) -> dict:
    """Deliver a signed webhook to a single subscriber with retry."""
    import hashlib as _hashlib
    from datetime import timedelta
    from pearl.db.models.idempotency import IdempotencyKeyRow

    idem_key = _hashlib.sha256(
        f"{envelope.event_id}:{sub.url}".encode("utf-8")
    ).hexdigest()

    # Idempotency check — skip if already delivered
    if db is not None:
        existing = await db.get(IdempotencyKeyRow, idem_key)
        if existing is not None and (
            existing.expires_at.replace(tzinfo=timezone.utc) if existing.expires_at.tzinfo is None
            else existing.expires_at
        ) > datetime.now(timezone.utc):
            logger.debug(
                "Webhook delivery skipped (idempotent): event_id=%s url=%s",
                envelope.event_id,
                sub.url,
            )
            return {"url": sub.url, "status": 200, "error": None, "idempotent": True}

    body_dict = envelope.model_dump(mode="json")
    body_bytes = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")
    signature = _sign_payload(body_bytes, sub.secret)
    body_dict["signature"] = signature

    signed_body = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Pearl-Signature": signature,
        "X-Pearl-Event": envelope.event_type,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(sub.url, content=signed_body, headers=headers)
                if resp.status_code < 300:
                    if db is not None:
                        now = datetime.now(timezone.utc)
                        db.add(IdempotencyKeyRow(
                            key_hash=idem_key,
                            endpoint=sub.url,
                            response_status=resp.status_code,
                            response_body={},
                            created_at=now,
                            expires_at=now + timedelta(hours=24),
                        ))
                        try:
                            await db.flush()
                        except Exception as flush_exc:
                            logger.debug("Idempotency key flush failed (non-fatal): %s", flush_exc)
                    return {"url": sub.url, "status": resp.status_code, "error": None}
                if resp.status_code == 429 and attempt < max_retries - 1:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2 ** attempt
                    except (ValueError, TypeError):
                        delay = 2 ** attempt
                    await asyncio.sleep(delay + random.random())
                    continue
                if resp.status_code >= 500 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt + random.random())
                    continue
                return {"url": sub.url, "status": resp.status_code, "error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt + random.random())
                continue
            logger.warning("Webhook delivery failed to %s: %s", sub.url, exc)
            return {"url": sub.url, "status": None, "error": str(exc)}

    return {"url": sub.url, "status": None, "error": "max retries exceeded"}
