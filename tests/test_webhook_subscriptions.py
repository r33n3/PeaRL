"""Tests for WebhookSubscription DB persistence."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_webhook_subscription_model_importable():
    """ORM model must be importable and have expected columns."""
    from pearl.db.models.webhook_subscription import WebhookSubscriptionRow
    cols = {c.name for c in WebhookSubscriptionRow.__table__.columns}
    assert "subscription_id" in cols
    assert "url" in cols
    assert "secret_hash" in cols
    assert "event_types" in cols
    assert "active" in cols
    assert "created_at" in cols


@pytest.mark.asyncio
async def test_webhook_subscription_repo_create_and_list(db_session: AsyncSession):
    """Repository can create and list subscriptions."""
    from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository

    repo = WebhookSubscriptionRepository(db_session)
    sub_id = await repo.create(
        url="https://example.com/hook",
        secret="mysecret",
        event_types=["project.created", "finding.ingested"],
    )
    assert sub_id.startswith("wsub_")

    subs = await repo.list_active()
    assert len(subs) == 1
    assert subs[0].url == "https://example.com/hook"
    assert subs[0].event_types == ["project.created", "finding.ingested"]
    assert subs[0].active is True


@pytest.mark.asyncio
async def test_webhook_subscription_repo_deactivate(db_session: AsyncSession):
    """Repository can deactivate a subscription by ID."""
    from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository

    repo = WebhookSubscriptionRepository(db_session)
    sub_id = await repo.create(url="https://example.com/hook2", secret="s2", event_types=[])
    await repo.deactivate(sub_id)
    await db_session.flush()

    subs = await repo.list_active()
    assert all(s.subscription_id != sub_id for s in subs)


@pytest.mark.asyncio
async def test_webhook_subscription_repo_get_subscribers_filters_by_event(db_session: AsyncSession):
    """get_subscribers returns only active subs matching event type."""
    from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository

    repo = WebhookSubscriptionRepository(db_session)
    await repo.create(url="https://a.com/hook", secret="s1", event_types=["project.created"])
    await repo.create(url="https://b.com/hook", secret="s2", event_types=["finding.ingested"])
    await repo.create(url="https://c.com/hook", secret="s3", event_types=[])  # catch-all

    subs = await repo.get_subscribers("project.created")
    urls = {s.url for s in subs}
    assert "https://a.com/hook" in urls
    assert "https://c.com/hook" in urls
    assert "https://b.com/hook" not in urls


@pytest.mark.asyncio
async def test_emit_event_queries_db_subscribers(db_session: AsyncSession):
    """emit_event uses DB subscriptions when db is provided."""
    from unittest.mock import patch
    from pearl.repositories.webhook_subscription_repo import WebhookSubscriptionRepository
    from pearl.events.webhook_emitter import emit_event

    repo = WebhookSubscriptionRepository(db_session)
    await repo.create(
        url="https://hook.example.com/receive",
        secret="test-secret",
        event_types=["test.happened"],
    )
    await db_session.flush()

    delivered_urls = []

    async def fake_deliver(envelope, sub, db=None):
        delivered_urls.append(sub.url)
        return {"url": sub.url, "status": 200, "error": None}

    with patch("pearl.events.webhook_emitter._deliver", side_effect=fake_deliver):
        results = await emit_event("test.happened", {"x": 1}, db=db_session)

    assert len(results) == 1
    assert delivered_urls == ["https://hook.example.com/receive"]


@pytest.mark.asyncio
async def test_emit_event_no_db_uses_in_memory_registry():
    """emit_event falls back to in-memory registry when db=None."""
    from unittest.mock import patch
    from pearl.events.webhook_config import WebhookSubscription
    from pearl.events.webhook_emitter import emit_event

    delivered = []

    async def fake_deliver(envelope, sub, db=None):
        delivered.append(sub.url)
        return {"url": sub.url, "status": 200, "error": None}

    with patch("pearl.events.webhook_emitter.webhook_registry") as mock_reg:
        mock_reg.get_subscribers.return_value = [
            WebhookSubscription(url="http://in-memory.com/hook", secret="s")
        ]
        with patch("pearl.events.webhook_emitter._deliver", side_effect=fake_deliver):
            await emit_event("any.event", {}, db=None)

    assert "http://in-memory.com/hook" in delivered
