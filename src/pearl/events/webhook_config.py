"""Webhook subscription management."""

from dataclasses import dataclass, field

from pearl.errors.exceptions import ConflictError


@dataclass
class WebhookSubscription:
    """A registered webhook endpoint."""

    url: str
    secret: str
    event_types: list[str] = field(default_factory=list)
    active: bool = True


class WebhookRegistry:
    """In-memory registry for webhook subscriptions.

    In production this would be backed by a database table.
    """

    def __init__(self, max_subscriptions: int = 100) -> None:
        self._subscriptions: list[WebhookSubscription] = []
        self._max_subscriptions = max_subscriptions

    def register(self, subscription: WebhookSubscription) -> None:
        if len(self._subscriptions) >= self._max_subscriptions:
            raise ConflictError(
                f"Webhook subscription limit reached ({self._max_subscriptions}). "
                "Remove an existing subscription before adding a new one."
            )
        self._subscriptions.append(subscription)

    def unregister(self, url: str) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.url != url]

    def get_subscribers(self, event_type: str) -> list[WebhookSubscription]:
        """Return active subscriptions matching the event type."""
        return [
            s
            for s in self._subscriptions
            if s.active and (not s.event_types or event_type in s.event_types)
        ]

    def list_all(self) -> list[WebhookSubscription]:
        return list(self._subscriptions)


# Module-level singleton — cap sourced from settings
from pearl.config import settings  # noqa: E402
webhook_registry = WebhookRegistry(max_subscriptions=settings.max_webhook_subscriptions)
