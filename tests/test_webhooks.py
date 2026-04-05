"""Tests for webhook event emission and signing."""

import hashlib
import hmac
import json

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
    from pearl.events.webhook_emitter import _deliver, build_envelope
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://fail.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with patch("pearl.events.webhook_emitter.random.random", return_value=0.5):
        with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
            mock_resp = AsyncMock()
            mock_resp.status_code = 503
            mock_resp.headers = {}
            with patch("httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=False)
                mock_instance.post = AsyncMock(return_value=mock_resp)
                mock_cls.return_value = mock_instance

                result = await _deliver(envelope, sub)

    assert result["error"] is not None
    # Deterministic: 2^0 + 0.5, 2^1 + 0.5 (no sleep on last failed attempt)
    assert sleep_calls == [1.5, 2.5]


@pytest.mark.asyncio
async def test_webhook_respects_retry_after_header():
    """429 response with Retry-After header uses that value for sleep."""
    from pearl.events.webhook_emitter import _deliver, build_envelope
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://ratelimit.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
        mock_resp = AsyncMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "5"}
        # After 429 sleep, return 200 to stop retrying
        mock_resp_ok = AsyncMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.headers = {}
        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=[mock_resp, mock_resp_ok])
            mock_cls.return_value = mock_instance

            result = await _deliver(envelope, sub)

    assert result["status"] == 200
    # First sleep should be ~5 (Retry-After) + jitter
    assert sleep_calls[0] >= 5.0


@pytest.mark.asyncio
async def test_webhook_retry_after_malformed_uses_backoff():
    """Malformed Retry-After header (e.g. HTTP-date) falls back to exponential backoff."""
    from pearl.events.webhook_emitter import _deliver, build_envelope
    from pearl.events.webhook_config import WebhookSubscription
    from unittest.mock import AsyncMock, patch

    sub = WebhookSubscription(url="http://ratelimit2.example.com/hook", secret="s")
    envelope = build_envelope("test.event", {})

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with patch("pearl.events.webhook_emitter.asyncio.sleep", side_effect=fake_sleep):
        mock_429 = AsyncMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}  # HTTP-date format

        mock_200 = AsyncMock()
        mock_200.status_code = 200
        mock_200.headers = {}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=[mock_429, mock_200])
            mock_cls.return_value = mock_instance

            result = await _deliver(envelope, sub)

    # Should not crash, should return 200 on retry
    assert result["status"] == 200
    assert result["error"] is None
    # Sleep was called (fallback backoff used)
    assert len(sleep_calls) >= 1
    # Fallback delay should be 2^0=1 + jitter, not some huge number
    assert sleep_calls[0] < 60
