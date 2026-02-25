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
