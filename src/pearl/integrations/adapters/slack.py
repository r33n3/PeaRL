"""Slack sink adapter — pushes security events and notifications via webhooks."""

from __future__ import annotations

import logging

import httpx

from pearl.integrations.adapters.base import SinkAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import (
    NormalizedNotification,
    NormalizedSecurityEvent,
)

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI: dict[str, str] = {
    "critical": "\U0001f534",  # 🔴
    "high": "\U0001f7e0",      # 🟠
    "moderate": "\U0001f7e1",  # 🟡
    "low": "\U0001f7e2",       # 🟢
}


class SlackAdapter(SinkAdapter):
    """Pushes messages to Slack via incoming webhooks.

    The webhook URL is stored in ``endpoint.base_url``.  Slack webhooks are
    pre-authenticated — no additional auth headers are required.
    """

    adapter_type: str = "slack"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Send a lightweight test message to the Slack webhook.

        Returns:
            True if Slack responds with 200.
        """
        payload = {"text": "PeaRL integration test"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint.base_url,
                    json=payload,
                    timeout=10.0,
                )
            if response.status_code == 200:
                logger.info("Slack connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "Slack connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Slack connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Push security event
    # ------------------------------------------------------------------

    async def push_event(
        self,
        endpoint: IntegrationEndpoint,
        event: NormalizedSecurityEvent,
    ) -> bool:
        """Push a security event as a Slack Block Kit message.

        Returns:
            True if delivery succeeded.
        """
        emoji = _SEVERITY_EMOJI.get(event.severity, "\u2753")  # ❓ fallback
        blocks = self._build_event_blocks(event, emoji)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint.base_url,
                    json={"blocks": blocks},
                    timeout=10.0,
                )
            if response.status_code == 200:
                logger.info(
                    "Slack event delivered for %s (event_type=%s)",
                    endpoint.endpoint_id,
                    event.event_type,
                )
                return True
            logger.warning(
                "Slack event delivery returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Slack event delivery failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Push notification
    # ------------------------------------------------------------------

    async def push_notification(
        self,
        endpoint: IntegrationEndpoint,
        notification: NormalizedNotification,
    ) -> bool:
        """Push a notification as a Slack Block Kit message.

        If the endpoint has a ``channel`` label it is included so the webhook
        can override its default channel (requires the webhook to be configured
        for channel overrides).

        Returns:
            True if delivery succeeded.
        """
        emoji = _SEVERITY_EMOJI.get(notification.severity, "\u2753")
        blocks = self._build_notification_blocks(notification, emoji)

        payload: dict = {"blocks": blocks}

        # Honour channel override from endpoint labels or the notification
        # itself.  Slack incoming webhooks can accept an optional ``channel``
        # field when the webhook app has been granted the necessary scope.
        channel = notification.channel
        if not channel and endpoint.labels:
            channel = endpoint.labels.get("channel")
        if channel:
            payload["channel"] = channel

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint.base_url,
                    json=payload,
                    timeout=10.0,
                )
            if response.status_code == 200:
                logger.info(
                    "Slack notification delivered for %s (subject=%s)",
                    endpoint.endpoint_id,
                    notification.subject,
                )
                return True
            logger.warning(
                "Slack notification delivery returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Slack notification delivery failed for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Push approval notification (interactive)
    # ------------------------------------------------------------------

    async def push_approval_notification(
        self,
        endpoint: IntegrationEndpoint,
        approval_id: str,
        project_id: str,
        request_type: str,
        environment: str,
        evidence_summary: str = "",
        dashboard_url: str = "",
    ) -> bool:
        """Push an approval request notification with interactive buttons.

        Builds a Slack Block Kit message with Approve, Reject, Request Info,
        and View in Dashboard buttons.

        Returns:
            True if delivery succeeded.
        """
        blocks = self._build_approval_blocks(
            approval_id=approval_id,
            project_id=project_id,
            request_type=request_type,
            environment=environment,
            evidence_summary=evidence_summary,
            dashboard_url=dashboard_url,
        )

        payload: dict = {"blocks": blocks}

        channel = None
        if endpoint.labels:
            channel = endpoint.labels.get("channel")
        if channel:
            payload["channel"] = channel

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint.base_url,
                    json=payload,
                    timeout=10.0,
                )
            if response.status_code == 200:
                logger.info(
                    "Slack approval notification delivered for %s (approval=%s)",
                    endpoint.endpoint_id,
                    approval_id,
                )
                return True
            logger.warning(
                "Slack approval notification returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Slack approval notification failed for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Block-building helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_event_blocks(
        event: NormalizedSecurityEvent,
        emoji: str,
    ) -> list[dict]:
        """Build Slack Block Kit blocks for a security event."""
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Security Event — {event.severity.upper()}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event.summary}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Event Type:*\n{event.event_type}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{event.project_id}"},
                    {"type": "mrkdwn", "text": f"*Timestamp:*\n{event.timestamp.isoformat()}"},
                ],
            },
        ]

        if event.finding_ids:
            ids_text = ", ".join(event.finding_ids)
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Finding IDs: {ids_text}"},
                    ],
                }
            )

        return blocks

    @staticmethod
    def _build_notification_blocks(
        notification: NormalizedNotification,
        emoji: str,
    ) -> list[dict]:
        """Build Slack Block Kit blocks for a notification."""
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.subject}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.body,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Severity: *{notification.severity}* "
                            f"| Project: *{notification.project_id}*"
                        ),
                    },
                ],
            },
        ]

        if notification.finding_ids:
            ids_text = ", ".join(notification.finding_ids)
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Finding IDs: {ids_text}"},
                    ],
                }
            )

        return blocks

    @staticmethod
    def _build_approval_blocks(
        approval_id: str,
        project_id: str,
        request_type: str,
        environment: str,
        evidence_summary: str = "",
        dashboard_url: str = "",
    ) -> list[dict]:
        """Build Slack Block Kit blocks for an approval request with interactive buttons."""
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "\U0001f6e1\ufe0f PeaRL Approval Required",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Request Type:*\n{request_type.replace('_', ' ').title()}"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{environment}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n`{project_id}`"},
                    {"type": "mrkdwn", "text": f"*Approval ID:*\n`{approval_id}`"},
                ],
            },
        ]

        if evidence_summary:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Evidence Summary:*\n{evidence_summary}",
                    },
                }
            )

        # Interactive buttons
        buttons: list[dict] = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "\u2705 Approve", "emoji": True},
                "style": "primary",
                "action_id": f"approve_{approval_id}",
                "value": approval_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "\u274c Reject", "emoji": True},
                "style": "danger",
                "action_id": f"reject_{approval_id}",
                "value": approval_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "\u2753 Request Info", "emoji": True},
                "action_id": f"request_info_{approval_id}",
                "value": approval_id,
            },
        ]

        if dashboard_url:
            buttons.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "\U0001f310 View in Dashboard", "emoji": True},
                    "url": f"{dashboard_url}/approvals/{approval_id}",
                    "action_id": f"view_{approval_id}",
                }
            )

        blocks.append({"type": "actions", "elements": buttons})

        return blocks
