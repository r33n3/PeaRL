"""Repository for persistent webhook subscriptions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.webhook_subscription import WebhookSubscriptionRow
from pearl.services.id_generator import generate_id


class WebhookSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, url: str, secret: str, event_types: list[str]) -> str:
        """Create a new active subscription. Returns subscription_id."""
        sub_id = generate_id("wsub_")
        row = WebhookSubscriptionRow(
            subscription_id=sub_id,
            url=url,
            secret=secret,
            event_types=event_types,
            active=True,
        )
        self._session.add(row)
        await self._session.flush()
        return sub_id

    async def deactivate(self, subscription_id: str) -> None:
        row = await self._session.get(WebhookSubscriptionRow, subscription_id)
        if row:
            row.active = False
            await self._session.flush()

    async def list_active(self) -> list[WebhookSubscriptionRow]:
        result = await self._session.execute(
            select(WebhookSubscriptionRow).where(WebhookSubscriptionRow.active.is_(True))
        )
        return list(result.scalars().all())

    async def get_subscribers(self, event_type: str) -> list[WebhookSubscriptionRow]:
        """Return active subscriptions matching event_type (or catch-all with empty event_types)."""
        rows = await self.list_active()
        return [
            r for r in rows
            if not r.event_types or event_type in r.event_types
        ]
