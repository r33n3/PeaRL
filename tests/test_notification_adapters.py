"""Tests for Teams, Telegram, and Webhook notification adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pearl.integrations.adapters.teams import TeamsAdapter
from pearl.integrations.adapters.telegram import TelegramAdapter
from pearl.integrations.adapters.webhook import WebhookAdapter
from pearl.integrations.config import AuthConfig, IntegrationEndpoint
from pearl.integrations.normalized import NormalizedNotification
from pearl.models.enums import IntegrationCategory, IntegrationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_endpoint(
    adapter_type: str,
    base_url: str = "https://example.com/webhook",
    labels: dict | None = None,
    auth: AuthConfig | None = None,
) -> IntegrationEndpoint:
    return IntegrationEndpoint(
        endpoint_id="intg_test001",
        name="Test Endpoint",
        adapter_type=adapter_type,
        integration_type=IntegrationType.SINK,
        category=IntegrationCategory.NOTIFICATION,
        base_url=base_url,
        auth=auth or AuthConfig(),
        labels=labels,
    )


def _make_notification(
    subject: str = "Test Alert",
    body: str = "Something happened.",
    severity: str = "high",
    project_id: str = "proj_test001",
) -> NormalizedNotification:
    return NormalizedNotification(
        subject=subject,
        body=body,
        severity=severity,
        project_id=project_id,
    )


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    return mock


# ---------------------------------------------------------------------------
# TeamsAdapter
# ---------------------------------------------------------------------------


class TestTeamsAdapter:
    @pytest.mark.asyncio
    async def test_push_notification_success(self):
        """push_notification returns True when Teams webhook responds 200."""
        adapter = TeamsAdapter()
        endpoint = _make_endpoint("teams", base_url="https://teams.example.com/hook")
        notification = _make_notification()

        mock_resp = _mock_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.teams.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert payload["@type"] == "MessageCard"
        assert payload["summary"] == notification.subject
        assert "sections" in payload

    @pytest.mark.asyncio
    async def test_push_notification_failure_logs_not_raises(self):
        """push_notification returns False (not raise) when httpx errors."""
        import httpx

        adapter = TeamsAdapter()
        endpoint = _make_endpoint("teams")
        notification = _make_notification()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch("pearl.integrations.adapters.teams.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_push_notification_non_200_returns_false(self):
        """push_notification returns False on a non-200 HTTP status."""
        adapter = TeamsAdapter()
        endpoint = _make_endpoint("teams")
        notification = _make_notification()

        mock_resp = _mock_response(503)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.teams.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_severity_color_critical(self):
        """Critical severity maps to red (FF0000)."""
        from pearl.integrations.adapters.teams import _SEVERITY_COLOR

        assert _SEVERITY_COLOR["critical"] == "FF0000"
        assert _SEVERITY_COLOR["high"] == "FF0000"

    @pytest.mark.asyncio
    async def test_severity_color_success(self):
        """Pass/success severity maps to green."""
        from pearl.integrations.adapters.teams import _SEVERITY_COLOR

        assert _SEVERITY_COLOR["pass"] == "28A745"
        assert _SEVERITY_COLOR["success"] == "28A745"

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """test_connection sends a test message and returns True on 200."""
        adapter = TeamsAdapter()
        endpoint = _make_endpoint("teams")

        mock_resp = _mock_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.teams.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.test_connection(endpoint)

        assert result is True


# ---------------------------------------------------------------------------
# TelegramAdapter
# ---------------------------------------------------------------------------


class TestTelegramAdapter:
    @pytest.mark.asyncio
    async def test_push_notification_formats_markdown(self):
        """push_notification sends Markdown text with parse_mode set."""
        import os

        adapter = TelegramAdapter()
        endpoint = _make_endpoint(
            "telegram",
            base_url="https://api.telegram.org",
            labels={"chat_id": "-1001234567890"},
            auth=AuthConfig(auth_type="bearer", bearer_token_env="TG_BOT_TOKEN"),
        )
        notification = _make_notification(subject="Gate Blocked", body="Needs review.")

        mock_resp = _mock_response(200, {"ok": True, "result": {}})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.dict(os.environ, {"TG_BOT_TOKEN": "bot:secret-token"}):
            with patch("pearl.integrations.adapters.telegram.httpx.AsyncClient", return_value=mock_client):
                result = await adapter.push_notification(endpoint, notification)

        assert result is True
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert payload["chat_id"] == "-1001234567890"
        assert payload["parse_mode"] == "Markdown"
        assert "*Gate Blocked*" in payload["text"]
        assert "Needs review." in payload["text"]

    @pytest.mark.asyncio
    async def test_test_connection_calls_getme(self):
        """test_connection calls /bot{token}/getMe."""
        import os

        adapter = TelegramAdapter()
        endpoint = _make_endpoint(
            "telegram",
            base_url="https://api.telegram.org",
            auth=AuthConfig(auth_type="bearer", bearer_token_env="TG_BOT_TOKEN"),
        )

        mock_resp = _mock_response(200, {"ok": True, "result": {"username": "my_bot"}})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch.dict(os.environ, {"TG_BOT_TOKEN": "bot:secret-token"}):
            with patch("pearl.integrations.adapters.telegram.httpx.AsyncClient", return_value=mock_client):
                result = await adapter.test_connection(endpoint)

        assert result is True
        call_args = mock_client.get.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/bot" in url
        assert "getMe" in url

    @pytest.mark.asyncio
    async def test_test_connection_no_token_returns_false(self):
        """test_connection returns False if no bot token can be resolved."""
        adapter = TelegramAdapter()
        endpoint = _make_endpoint(
            "telegram",
            base_url="https://api.telegram.org",
            # No auth configured — token will not resolve
        )
        result = await adapter.test_connection(endpoint)
        assert result is False

    @pytest.mark.asyncio
    async def test_push_notification_no_chat_id_returns_false(self):
        """push_notification returns False if chat_id label is missing."""
        import os

        adapter = TelegramAdapter()
        endpoint = _make_endpoint(
            "telegram",
            base_url="https://api.telegram.org",
            labels={},  # no chat_id
            auth=AuthConfig(auth_type="bearer", bearer_token_env="TG_BOT_TOKEN"),
        )
        notification = _make_notification()

        with patch.dict(os.environ, {"TG_BOT_TOKEN": "bot:secret-token"}):
            result = await adapter.push_notification(endpoint, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_push_notification_http_error_returns_false(self):
        """push_notification returns False (not raise) on httpx error."""
        import os
        import httpx

        adapter = TelegramAdapter()
        endpoint = _make_endpoint(
            "telegram",
            base_url="https://api.telegram.org",
            labels={"chat_id": "-1001234567890"},
            auth=AuthConfig(auth_type="bearer", bearer_token_env="TG_BOT_TOKEN"),
        )
        notification = _make_notification()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch.dict(os.environ, {"TG_BOT_TOKEN": "bot:secret-token"}):
            with patch("pearl.integrations.adapters.telegram.httpx.AsyncClient", return_value=mock_client):
                result = await adapter.push_notification(endpoint, notification)

        assert result is False


# ---------------------------------------------------------------------------
# WebhookAdapter
# ---------------------------------------------------------------------------


class TestWebhookAdapter:
    @pytest.mark.asyncio
    async def test_push_notification_includes_content_for_discord(self):
        """push_notification includes a 'content' key for Discord compatibility."""
        adapter = WebhookAdapter()
        endpoint = _make_endpoint("webhook", base_url="https://discord.com/api/webhooks/xxx")
        notification = _make_notification(subject="Alert", body="Gate failed.")

        mock_resp = _mock_response(204)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is True
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert "content" in payload
        assert "Alert" in payload["content"]
        assert payload["title"] == "Alert"
        assert payload["body"] == "Gate failed."
        assert payload["severity"] == "high"
        assert payload["project_id"] == "proj_test001"

    @pytest.mark.asyncio
    async def test_push_notification_returns_false_on_error(self):
        """push_notification returns False (not raise) when httpx raises."""
        import httpx

        adapter = WebhookAdapter()
        endpoint = _make_endpoint("webhook")
        notification = _make_notification()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("pearl.integrations.adapters.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_push_notification_4xx_returns_false(self):
        """push_notification returns False on a 4xx status."""
        adapter = WebhookAdapter()
        endpoint = _make_endpoint("webhook")
        notification = _make_notification()

        mock_resp = _mock_response(401)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.push_notification(endpoint, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """test_connection returns True when HEAD returns sub-400 status."""
        adapter = WebhookAdapter()
        endpoint = _make_endpoint("webhook")

        mock_resp = _mock_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_resp)

        with patch("pearl.integrations.adapters.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.test_connection(endpoint)

        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_falls_back_to_get_on_405(self):
        """test_connection falls back to GET when HEAD returns 405."""
        adapter = WebhookAdapter()
        endpoint = _make_endpoint("webhook")

        mock_resp_head = _mock_response(405)
        mock_resp_get = _mock_response(200)

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_resp_head)
        mock_client.get = AsyncMock(return_value=mock_resp_get)

        with patch.object(adapter, "_get_client", return_value=mock_client):
            result = await adapter.test_connection(endpoint)

        assert result is True


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_three_new_adapters_registered(self):
        """Teams, Telegram, and Webhook adapters appear in AVAILABLE_ADAPTERS."""
        from pearl.integrations.adapters import AVAILABLE_ADAPTERS

        assert "teams" in AVAILABLE_ADAPTERS
        assert "telegram" in AVAILABLE_ADAPTERS
        assert "webhook" in AVAILABLE_ADAPTERS

    def test_import_adapter_teams(self):
        """import_adapter resolves TeamsAdapter correctly."""
        from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter

        cls = import_adapter(AVAILABLE_ADAPTERS["teams"])
        assert cls.__name__ == "TeamsAdapter"

    def test_import_adapter_telegram(self):
        """import_adapter resolves TelegramAdapter correctly."""
        from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter

        cls = import_adapter(AVAILABLE_ADAPTERS["telegram"])
        assert cls.__name__ == "TelegramAdapter"

    def test_import_adapter_webhook(self):
        """import_adapter resolves WebhookAdapter correctly."""
        from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter

        cls = import_adapter(AVAILABLE_ADAPTERS["webhook"])
        assert cls.__name__ == "WebhookAdapter"
