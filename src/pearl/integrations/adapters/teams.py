"""Microsoft Teams sink adapter — pushes notifications via incoming webhook URLs."""

from __future__ import annotations

import logging

import httpx

from pearl.integrations.adapters.base import SinkAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedNotification, NormalizedSecurityEvent

logger = logging.getLogger(__name__)

# Severity → Teams theme colour (hex without #)
_SEVERITY_COLOR: dict[str, str] = {
    "critical": "FF0000",
    "high": "FF0000",
    "moderate": "FFA500",
    "medium": "FFA500",
    "low": "0078D4",
    "info": "0078D4",
    "pass": "28A745",
    "success": "28A745",
}

_DEFAULT_COLOR = "0078D4"


class TeamsAdapter(SinkAdapter):
    """Pushes messages to Microsoft Teams via incoming webhooks.

    The webhook URL is stored in ``endpoint.base_url``.  Teams incoming
    webhooks are pre-authenticated — no additional auth headers are required.
    """

    adapter_type: str = "teams"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Send a lightweight test message to the Teams webhook.

        Returns:
            True if Teams responds with a 200 OK.
        """
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": _DEFAULT_COLOR,
            "summary": "PeaRL integration test",
            "sections": [
                {
                    "activityTitle": "PeaRL integration test",
                    "activityText": "This is a connectivity test from PeaRL.",
                }
            ],
        }
        try:
            client = await self._get_client()
            response = await client.post(
                endpoint.base_url,
                json=payload,
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.info(
                    "Teams connection test succeeded for %s", endpoint.endpoint_id
                )
                return True
            logger.warning(
                "Teams connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Teams connection test failed for %s: %s", endpoint.endpoint_id, exc
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
        """Push a security event as a Teams MessageCard.

        Returns:
            True if delivery succeeded.
        """
        color = _SEVERITY_COLOR.get(event.severity, _DEFAULT_COLOR)
        facts = [
            {"name": "Event Type", "value": event.event_type},
            {"name": "Project", "value": event.project_id},
            {"name": "Timestamp", "value": event.timestamp.isoformat()},
        ]
        if event.finding_ids:
            facts.append({"name": "Finding IDs", "value": ", ".join(event.finding_ids)})

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": event.summary,
            "sections": [
                {
                    "activityTitle": f"Security Event — {event.severity.upper()}",
                    "activityText": event.summary,
                    "facts": facts,
                }
            ],
        }

        try:
            client = await self._get_client()
            response = await client.post(
                endpoint.base_url,
                json=payload,
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.info(
                    "Teams event delivered for %s (event_type=%s)",
                    endpoint.endpoint_id,
                    event.event_type,
                )
                return True
            logger.warning(
                "Teams event delivery returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Teams event delivery failed for %s: %s", endpoint.endpoint_id, exc
            )
            return False

    # ------------------------------------------------------------------
    # Push notification
    # ------------------------------------------------------------------

    async def push_notification(
        self,
        endpoint: IntegrationEndpoint,
        notification: NormalizedNotification,
    ) -> bool:
        """Push a notification as a Teams MessageCard.

        Returns:
            True if delivery succeeded.
        """
        color = _SEVERITY_COLOR.get(notification.severity, _DEFAULT_COLOR)
        facts = [
            {"name": "Severity", "value": notification.severity},
            {"name": "Project", "value": notification.project_id},
        ]
        if notification.finding_ids:
            facts.append(
                {"name": "Finding IDs", "value": ", ".join(notification.finding_ids)}
            )

        payload: dict = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": notification.subject,
            "sections": [
                {
                    "activityTitle": notification.subject,
                    "activityText": notification.body,
                    "facts": facts,
                }
            ],
        }

        try:
            client = await self._get_client()
            response = await client.post(
                endpoint.base_url,
                json=payload,
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.info(
                    "Teams notification delivered for %s (subject=%s)",
                    endpoint.endpoint_id,
                    notification.subject,
                )
                return True
            logger.warning(
                "Teams notification delivery returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Teams notification delivery failed for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return False
