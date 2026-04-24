"""Telegram sink adapter — pushes notifications via the Telegram Bot API."""

from __future__ import annotations

import structlog

import httpx

from pearl.integrations.adapters.base import SinkAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedNotification, NormalizedSecurityEvent

logger = structlog.get_logger(__name__)


class TelegramAdapter(SinkAdapter):
    """Pushes messages to Telegram via the Bot API.

    Configuration:
    - ``endpoint.base_url``: Telegram API base, e.g. ``https://api.telegram.org``
    - ``endpoint.auth.bearer_token_env``: env var that holds the bot token
    - ``endpoint.labels["chat_id"]``: target chat or channel ID (e.g. ``-1001234567890``)

    The bot token is stored as the value of the env var referenced by
    ``endpoint.auth.bearer_token_env`` — it is never stored directly.
    """

    adapter_type: str = "telegram"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bot_token(self, endpoint: IntegrationEndpoint) -> str | None:
        """Resolve the bot token from the endpoint auth config."""
        return endpoint.auth.resolve_bearer_token()

    def _base(self, endpoint: IntegrationEndpoint) -> str:
        return endpoint.base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Call ``/bot{token}/getMe`` to verify the bot token is valid.

        Returns:
            True if the Telegram API confirms the token is active.
        """
        token = self._bot_token(endpoint)
        if not token:
            logger.warning(
                "Telegram connection test: no bot token resolved for %s",
                endpoint.endpoint_id,
            )
            return False

        url = f"{self._base(endpoint)}/bot{token}/getMe"
        try:
            client = await self._get_client()
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200 and response.json().get("ok"):
                logger.info(
                    "Telegram connection test succeeded for %s", endpoint.endpoint_id
                )
                return True
            logger.warning(
                "Telegram connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Telegram connection test failed for %s: %s", endpoint.endpoint_id, exc
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
        """Push a security event as a Telegram Markdown message.

        Returns:
            True if delivery succeeded.
        """
        token = self._bot_token(endpoint)
        if not token:
            logger.warning(
                "Telegram push_event: no bot token resolved for %s",
                endpoint.endpoint_id,
            )
            return False

        chat_id = (endpoint.labels or {}).get("chat_id")
        if not chat_id:
            logger.warning(
                "Telegram push_event: no chat_id label for %s", endpoint.endpoint_id
            )
            return False

        text = (
            f"*Security Event — {event.severity.upper()}*\n\n"
            f"{event.summary}\n\n"
            f"Type: `{event.event_type}`\n"
            f"Project: `{event.project_id}`\n"
            f"Timestamp: {event.timestamp.isoformat()}"
        )
        if event.finding_ids:
            text += f"\nFindings: {', '.join(event.finding_ids)}"

        return await self._send_message(endpoint, token, chat_id, text)

    # ------------------------------------------------------------------
    # Push notification
    # ------------------------------------------------------------------

    async def push_notification(
        self,
        endpoint: IntegrationEndpoint,
        notification: NormalizedNotification,
    ) -> bool:
        """Push a notification as a Telegram Markdown message.

        Format: ``*{subject}*\\n\\n{body}``

        Returns:
            True if delivery succeeded.
        """
        token = self._bot_token(endpoint)
        if not token:
            logger.warning(
                "Telegram push_notification: no bot token resolved for %s",
                endpoint.endpoint_id,
            )
            return False

        chat_id = (endpoint.labels or {}).get("chat_id")
        if not chat_id:
            logger.warning(
                "Telegram push_notification: no chat_id label for %s",
                endpoint.endpoint_id,
            )
            return False

        text = f"*{notification.subject}*\n\n{notification.body}"

        if notification.finding_ids:
            text += f"\n\nFindings: {', '.join(notification.finding_ids)}"

        return await self._send_message(endpoint, token, chat_id, text)

    # ------------------------------------------------------------------
    # Shared send helper
    # ------------------------------------------------------------------

    async def _send_message(
        self,
        endpoint: IntegrationEndpoint,
        token: str,
        chat_id: str,
        text: str,
    ) -> bool:
        """POST a sendMessage request to the Telegram Bot API.

        Returns:
            True on success, False on any error (never raises).
        """
        url = f"{self._base(endpoint)}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            client = await self._get_client()
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200 and response.json().get("ok"):
                logger.info(
                    "Telegram message delivered for %s", endpoint.endpoint_id
                )
                return True
            logger.warning(
                "Telegram sendMessage returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Telegram sendMessage failed for %s: %s", endpoint.endpoint_id, exc
            )
            return False
