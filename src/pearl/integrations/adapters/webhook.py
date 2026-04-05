"""Generic webhook sink adapter — pushes events/notifications via HTTP POST.

Compatible with Discord, custom endpoints, and any service that accepts a JSON
POST body.
"""

from __future__ import annotations

import logging

import httpx

from pearl.integrations.adapters.base import SinkAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedNotification, NormalizedSecurityEvent

logger = logging.getLogger(__name__)


class WebhookAdapter(SinkAdapter):
    """Pushes messages to a generic HTTP webhook (Discord, custom, etc.).

    The target URL is stored in ``endpoint.base_url``.  Optional HTTP headers
    for authentication (e.g. ``Authorization: Bearer …``) are resolved via the
    ``endpoint.auth`` config.
    """

    adapter_type: str = "webhook"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Attempt a HEAD (or GET) on the base URL to check reachability.

        Returns:
            True if the server responds without a 4xx or 5xx status.
        """
        headers = endpoint.auth.get_headers() if endpoint.auth else {}
        try:
            client = await self._get_client()
            response = await client.head(
                endpoint.base_url,
                headers=headers,
                timeout=10.0,
            )
            # HEAD may return 405 on some webhooks — fall back to GET
            if response.status_code == 405:
                response = await client.get(
                    endpoint.base_url,
                    headers=headers,
                    timeout=10.0,
                )
            if response.status_code < 400:
                logger.info(
                    "Webhook connection test succeeded for %s", endpoint.endpoint_id
                )
                return True
            logger.warning(
                "Webhook connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Webhook connection test failed for %s: %s", endpoint.endpoint_id, exc
            )
            return False

    # ------------------------------------------------------------------
    # Push security event
    # ------------------------------------------------------------------

    async def push_event(
        self,
        endpoint: IntegrationEndpoint,
        event: NormalizedSecurityEvent,
    ) -> bool:
        """Push a security event as a JSON POST to the webhook URL.

        Includes a ``content`` field for Discord compatibility.

        Returns:
            True if delivery succeeded.
        """
        summary = event.summary
        payload: dict = {
            "event_type": event.event_type,
            "severity": event.severity,
            "summary": summary,
            "project_id": event.project_id,
            "timestamp": event.timestamp.isoformat(),
            "details": event.details,
            "finding_ids": event.finding_ids,
            # Discord-compatible field
            "content": f"**Security Event — {event.severity.upper()}**\n{summary}",
        }

        return await self._post(endpoint, payload, context="event")

    # ------------------------------------------------------------------
    # Push notification
    # ------------------------------------------------------------------

    async def push_notification(
        self,
        endpoint: IntegrationEndpoint,
        notification: NormalizedNotification,
    ) -> bool:
        """Push a notification as a JSON POST to the webhook URL.

        Includes a ``content`` field for Discord compatibility.

        Returns:
            True if delivery succeeded.
        """
        payload: dict = {
            "title": notification.subject,
            "body": notification.body,
            "severity": notification.severity,
            "project_id": notification.project_id,
            "finding_ids": notification.finding_ids,
            # Discord-compatible field
            "content": f"**{notification.subject}**\n{notification.body}",
        }

        return await self._post(endpoint, payload, context="notification")

    # ------------------------------------------------------------------
    # Shared POST helper
    # ------------------------------------------------------------------

    async def _post(
        self,
        endpoint: IntegrationEndpoint,
        payload: dict,
        context: str = "message",
    ) -> bool:
        """POST JSON payload to endpoint.base_url.

        Returns:
            True on 2xx response, False otherwise (never raises).
        """
        headers = endpoint.auth.get_headers() if endpoint.auth else {}
        headers.setdefault("Content-Type", "application/json")

        try:
            client = await self._get_client()
            response = await client.post(
                endpoint.base_url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if 200 <= response.status_code < 300:
                logger.info(
                    "Webhook %s delivered for %s", context, endpoint.endpoint_id
                )
                return True
            logger.warning(
                "Webhook %s returned %s for %s",
                context,
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Webhook %s failed for %s: %s", context, endpoint.endpoint_id, exc
            )
            return False
