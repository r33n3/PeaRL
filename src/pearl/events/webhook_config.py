"""Webhook subscription management."""

from dataclasses import dataclass, field


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

    def __init__(self) -> None:
        self._subscriptions: list[WebhookSubscription] = []

    def register(self, subscription: WebhookSubscription) -> None:
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


# Module-level singleton
webhook_registry = WebhookRegistry()
