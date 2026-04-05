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
) -> list[dict]:
    """Emit a webhook event to all matching subscribers.

    Returns a list of delivery results (url, status, error).
    """
    subscribers = webhook_registry.get_subscribers(event_type)
    if not subscribers:
        return []

    envelope = build_envelope(event_type, payload, source_system)
    results = []

    for sub in subscribers:
        result = await _deliver(envelope, sub)
        results.append(result)

    return results


async def _deliver(envelope: WebhookEnvelope, sub: WebhookSubscription) -> dict:
    """Deliver a signed webhook to a single subscriber with retry."""
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
