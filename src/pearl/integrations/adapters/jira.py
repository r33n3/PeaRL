"""Jira sink adapter — creates issues in Jira Cloud via the REST v3 API."""

from __future__ import annotations

import logging

import httpx

from pearl.integrations.adapters.base import SinkAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import (
    NormalizedSecurityEvent,
    NormalizedTicket,
)

logger = logging.getLogger(__name__)

# Maps PeaRL severity / priority values to Jira priority names.
_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high": "High",
    "moderate": "Medium",
    "medium": "Medium",
    "low": "Low",
}


class JiraAdapter(SinkAdapter):
    """Creates issues in Jira Cloud.

    Authentication is handled via ``endpoint.auth.get_headers()`` which should
    return Basic-auth headers (email + API token) for Jira Cloud.

    Endpoint labels:
        ``project_key`` — Jira project key (default ``"SEC"``).
        ``issue_type``  — Issue type name (default ``"Bug"``).
    """

    adapter_type: str = "jira"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify credentials by calling ``/rest/api/3/myself``.

        Returns:
            True if Jira responds with 200.
        """
        url = f"{endpoint.base_url.rstrip('/')}/rest/api/3/myself"
        headers = endpoint.auth.get_headers()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info("Jira connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "Jira connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Jira connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Push security event
    # ------------------------------------------------------------------

    async def push_event(
        self,
        endpoint: IntegrationEndpoint,
        event: NormalizedSecurityEvent,
    ) -> bool:
        """Create a Jira issue from a security event.

        Returns:
            True if issue creation succeeded (201).
        """
        labels = endpoint.labels or {}
        project_key = labels.get("project_key", "SEC")
        issue_type = labels.get("issue_type", "Bug")

        description = self._format_event_description(event)
        priority_name = _PRIORITY_MAP.get(event.severity, "Medium")

        payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": event.summary,
                "description": description,
                "priority": {"name": priority_name},
                "labels": ["pearl-security", f"severity-{event.severity}"],
            }
        }

        return await self._create_issue(endpoint, payload, context=f"event:{event.event_type}")

    # ------------------------------------------------------------------
    # Push ticket
    # ------------------------------------------------------------------

    async def push_ticket(
        self,
        endpoint: IntegrationEndpoint,
        ticket: NormalizedTicket,
    ) -> bool:
        """Create a Jira issue from a normalized ticket.

        Returns:
            True if issue creation succeeded (201).
        """
        labels = endpoint.labels or {}
        project_key = labels.get("project_key", "SEC")
        issue_type = labels.get("issue_type", "Bug")

        priority_name = _PRIORITY_MAP.get(ticket.priority, "Medium")

        fields: dict = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": ticket.title,
            "description": ticket.description,
            "priority": {"name": priority_name},
            "labels": ticket.labels if ticket.labels else [],
        }

        if ticket.assignee:
            fields["assignee"] = {"accountId": ticket.assignee}

        payload = {"fields": fields}

        return await self._create_issue(endpoint, payload, context=f"ticket:{ticket.title}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _create_issue(
        self,
        endpoint: IntegrationEndpoint,
        payload: dict,
        *,
        context: str = "",
    ) -> bool:
        """POST ``/rest/api/3/issue`` and return True on 201."""
        url = f"{endpoint.base_url.rstrip('/')}/rest/api/3/issue"
        headers = {
            **endpoint.auth.get_headers(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=15.0,
                )
            if response.status_code == 201:
                issue_key = response.json().get("key", "?")
                logger.info(
                    "Jira issue %s created for %s (%s)",
                    issue_key,
                    endpoint.endpoint_id,
                    context,
                )
                return True
            logger.warning(
                "Jira issue creation returned %s for %s (%s): %s",
                response.status_code,
                endpoint.endpoint_id,
                context,
                response.text[:500],
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "Jira issue creation failed for %s (%s): %s",
                endpoint.endpoint_id,
                context,
                exc,
            )
            return False

    @staticmethod
    def _format_event_description(event: NormalizedSecurityEvent) -> str:
        """Build a plain-text description suitable for Jira's description field."""
        lines = [
            f"Security Event: {event.event_type}",
            f"Severity: {event.severity}",
            f"Project: {event.project_id}",
            f"Timestamp: {event.timestamp.isoformat()}",
            "",
            event.summary,
        ]

        if event.details:
            lines.append("")
            lines.append("Details:")
            for key, value in event.details.items():
                lines.append(f"  {key}: {value}")

        if event.finding_ids:
            lines.append("")
            lines.append(f"Finding IDs: {', '.join(event.finding_ids)}")

        return "\n".join(lines)
