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
