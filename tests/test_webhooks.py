"""Tests for webhook event emission and signing."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from pearl.events.webhook_config import WebhookRegistry, WebhookSubscription
from pearl.events.webhook_emitter import _sign_payload, build_envelope


def test_build_envelope():
    """Envelope has all required fields."""
    envelope = build_envelope("project.created", {"project_id": "proj_test"})
    assert envelope.event_type == "project.created"
    assert envelope.source_system == "pearl-api"
    assert envelope.schema_version == "1.1"
    assert envelope.event_id.startswith("evt_")
    assert envelope.payload == {"project_id": "proj_test"}
    assert envelope.signature is None  # Unsigned until delivery


def test_sign_payload():
    """HMAC-SHA256 signature is correct."""
    body = b'{"test":"data"}'
    secret = "my-secret"
    sig = _sign_payload(body, secret)
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert sig == expected


def test_webhook_registry():
    """Registry filters subscribers by event type."""
    registry = WebhookRegistry()
    sub_all = WebhookSubscription(url="http://a.com/hook", secret="s1")
    sub_specific = WebhookSubscription(
        url="http://b.com/hook", secret="s2", event_types=["project.created"]
    )
    sub_inactive = WebhookSubscription(
        url="http://c.com/hook", secret="s3", active=False
    )
    registry.register(sub_all)
    registry.register(sub_specific)
    registry.register(sub_inactive)

    # "project.created" matches sub_all (no filter) and sub_specific
    subs = registry.get_subscribers("project.created")
    assert len(subs) == 2

    # "job.completed" matches only sub_all
    subs = registry.get_subscribers("job.completed")
    assert len(subs) == 1
    assert subs[0].url == "http://a.com/hook"


def test_webhook_registry_unregister():
    """Unregistering removes the subscription."""
    registry = WebhookRegistry()
    registry.register(WebhookSubscription(url="http://a.com/hook", secret="s1"))
    registry.register(WebhookSubscription(url="http://b.com/hook", secret="s2"))
    registry.unregister("http://a.com/hook")
    assert len(registry.list_all()) == 1
    assert registry.list_all()[0].url == "http://b.com/hook"


def test_envelope_validates_against_schema():
    """Envelope serialization matches webhook-envelope schema structure."""
    envelope = build_envelope("finding.ingested", {"count": 5})
    data = envelope.model_dump(mode="json")
    assert "schema_version" in data
    assert "event_type" in data
    assert "event_id" in data
    assert "occurred_at" in data
    assert "source_system" in data
    assert "payload" in data


@pytest.mark.asyncio
async def test_webhook_retry_uses_backoff():
    """Each retry attempt sleeps before the next attempt."""
    from pearl.events.webhook_emitter import _deliver, build_envelope, _webhook_client
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://fail.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    mock_resp = AsyncMock()
    mock_resp.status_code = 503
    mock_resp.headers = {}

    with patch("pearl.events.webhook_emitter.random.random", return_value=0.5):
        with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
            with patch.object(_webhook_client, "post", AsyncMock(return_value=mock_resp)):
                result = await _deliver(envelope, sub)

    assert result["error"] is not None
    # Deterministic: 2^0 + 0.5, 2^1 + 0.5 (no sleep on last failed attempt)
    assert sleep_calls == [1.5, 2.5]


@pytest.mark.asyncio
async def test_webhook_respects_retry_after_header():
    """429 response with Retry-After header uses that value for sleep."""
    from pearl.events.webhook_emitter import _deliver, build_envelope, _webhook_client
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://ratelimit.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    mock_resp = AsyncMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "5"}
    # After 429 sleep, return 200 to stop retrying
    mock_resp_ok = AsyncMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.headers = {}

    with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
        with patch.object(_webhook_client, "post", AsyncMock(side_effect=[mock_resp, mock_resp_ok])):
            result = await _deliver(envelope, sub)

    assert result["status"] == 200
    # First sleep should be ~5 (Retry-After) + jitter
    assert sleep_calls[0] >= 5.0


@pytest.mark.asyncio
async def test_webhook_retry_after_malformed_uses_backoff():
    """Malformed Retry-After header (e.g. HTTP-date) falls back to exponential backoff."""
    from pearl.events.webhook_emitter import _deliver, build_envelope, _webhook_client
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://ratelimit2.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    mock_429 = AsyncMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}  # HTTP-date format

    mock_200 = AsyncMock()
    mock_200.status_code = 200
    mock_200.headers = {}

    with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
        with patch.object(_webhook_client, "post", AsyncMock(side_effect=[mock_429, mock_200])):
            result = await _deliver(envelope, sub)

    # Should not crash, should return 200 on retry
    assert result["status"] == 200
    assert result["error"] is None
    # Sleep was called (fallback backoff used)
    assert len(sleep_calls) >= 1
    # Fallback delay should be 2^0=1 + jitter, not some huge number
    assert sleep_calls[0] < 60


@pytest.mark.asyncio
async def test_webhook_idempotency_skips_duplicate(db_session):
    """Pre-seeded idempotency key causes _deliver to skip HTTP delivery."""
    from datetime import timedelta
    import hashlib
    from pearl.events.webhook_emitter import _deliver, build_envelope
    from pearl.events.webhook_config import WebhookSubscription
    from pearl.db.models.idempotency import IdempotencyKeyRow

    sub = WebhookSubscription(url="http://idem.example.com/hook", secret="idem-secret")
    envelope = build_envelope("test.idempotency", {"x": 1})

    idem_key = hashlib.sha256(
        f"{envelope.event_id}:{sub.url}".encode("utf-8")
    ).hexdigest()

    # Pre-seed: delivery already happened
    now = datetime.now(timezone.utc)
    db_session.add(IdempotencyKeyRow(
        key_hash=idem_key,
        endpoint=sub.url,
        response_status=200,
        response_body={},
        created_at=now,
        expires_at=now + timedelta(hours=24),
    ))
    await db_session.flush()

    # _deliver must skip HTTP and return idempotent=True
    result = await _deliver(envelope, sub, db=db_session)

    assert result.get("idempotent") is True
    assert result["status"] == 200
    assert result["error"] is None


@pytest.mark.asyncio
async def test_webhook_idempotency_stores_key_on_success(db_session):
    """After a successful delivery with db session, idempotency key is stored."""
    import hashlib
    from unittest.mock import AsyncMock, patch
    from pearl.events.webhook_emitter import _deliver, build_envelope, _webhook_client
    from pearl.events.webhook_config import WebhookSubscription
    from pearl.db.models.idempotency import IdempotencyKeyRow

    sub = WebhookSubscription(url="http://store-test.example.com/hook", secret="s")
    envelope = build_envelope("test.store", {})

    idem_key = hashlib.sha256(
        f"{envelope.event_id}:{sub.url}".encode("utf-8")
    ).hexdigest()

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}

    with patch.object(_webhook_client, "post", AsyncMock(return_value=mock_resp)):
        result = await _deliver(envelope, sub, db=db_session)

    assert result["status"] == 200
    assert result.get("idempotent") is not True  # Was a real delivery

    # Key must be stored in DB
    stored = await db_session.get(IdempotencyKeyRow, idem_key)
    assert stored is not None
    assert stored.endpoint == sub.url


def test_webhook_registry_enforces_subscription_cap():
    """Registering beyond max_subscriptions raises ConflictError."""
    from pearl.errors.exceptions import ConflictError

    registry = WebhookRegistry(max_subscriptions=3)
    for i in range(3):
        registry.register(WebhookSubscription(url=f"http://host{i}.example.com/hook", secret="s"))

    with pytest.raises(ConflictError, match="limit"):
        registry.register(WebhookSubscription(url="http://overflow.example.com/hook", secret="s"))

    # Existing subscriptions must be unchanged
    assert len(registry.list_all()) == 3


import httpx
from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_deliver_reuses_single_client_across_retries():
    """_deliver must not instantiate a new AsyncClient per retry attempt."""
    from pearl.events.webhook_emitter import _deliver, _webhook_client
    from pearl.events.webhook_config import WebhookSubscription
    from pearl.events.webhook_emitter import build_envelope

    envelope = build_envelope("test.event", {"x": 1})
    sub = WebhookSubscription(url="http://example.com/hook", secret="s")

    post_call_count = 0

    async def fake_post(url, **kwargs):
        nonlocal post_call_count
        post_call_count += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 500  # force retries
        mock_resp.headers = {}
        return mock_resp

    with patch.object(_webhook_client, "post", side_effect=fake_post):
        result = await _deliver(envelope, sub, db=None)

    # 3 retries happened, but only the one shared client was used
    assert post_call_count == 3
    assert result["error"] is not None
