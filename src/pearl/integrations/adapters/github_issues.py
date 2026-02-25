"""GitHub Issues sink adapter — creates issues via the GitHub REST API."""

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


class GitHubIssuesAdapter(SinkAdapter):
    """Creates issues in a GitHub repository.

    Authentication is handled via ``endpoint.auth.get_headers()`` which should
    return a ``Bearer`` token header for the GitHub API.

    Endpoint labels:
        ``owner`` — GitHub repository owner (org or user).
        ``repo``  — GitHub repository name.
    """

    adapter_type: str = "github_issues"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify credentials by calling ``GET /user``.

        Returns:
            True if GitHub responds with 200.
        """
        url = f"{endpoint.base_url.rstrip('/')}/user"
        headers = {
            **endpoint.auth.get_headers(),
            "Accept": "application/vnd.github+json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info(
                    "GitHub connection test succeeded for %s",
                    endpoint.endpoint_id,
                )
                return True
            logger.warning(
                "GitHub connection test returned %s for %s",
                response.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "GitHub connection test failed for %s: %s",
                endpoint.endpoint_id,
                exc,
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
        """Create a GitHub issue from a security event.

        Returns:
            True if issue creation succeeded (201).
        """
        owner, repo = self._get_owner_repo(endpoint)
        if not owner or not repo:
            logger.error(
                "GitHub adapter requires 'owner' and 'repo' labels on endpoint %s",
                endpoint.endpoint_id,
            )
            return False

        body = self._format_event_body(event)
        labels = ["pearl-security", f"severity:{event.severity}"]

        payload = {
            "title": event.summary,
            "body": body,
            "labels": labels,
        }

        return await self._create_issue(endpoint, owner, repo, payload, context=f"event:{event.event_type}")

    # ------------------------------------------------------------------
    # Push ticket
    # ------------------------------------------------------------------

    async def push_ticket(
        self,
        endpoint: IntegrationEndpoint,
        ticket: NormalizedTicket,
    ) -> bool:
        """Create a GitHub issue from a normalized ticket.

        Returns:
            True if issue creation succeeded (201).
        """
        owner, repo = self._get_owner_repo(endpoint)
        if not owner or not repo:
            logger.error(
                "GitHub adapter requires 'owner' and 'repo' labels on endpoint %s",
                endpoint.endpoint_id,
            )
            return False

        payload: dict = {
            "title": ticket.title,
            "body": ticket.description,
            "labels": ticket.labels if ticket.labels else [],
        }

        if ticket.assignee:
            payload["assignees"] = [ticket.assignee]

        return await self._create_issue(endpoint, owner, repo, payload, context=f"ticket:{ticket.title}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_owner_repo(endpoint: IntegrationEndpoint) -> tuple[str | None, str | None]:
        """Extract ``owner`` and ``repo`` from endpoint labels."""
        labels = endpoint.labels or {}
        return labels.get("owner"), labels.get("repo")

    async def _create_issue(
        self,
        endpoint: IntegrationEndpoint,
        owner: str,
        repo: str,
        payload: dict,
        *,
        context: str = "",
    ) -> bool:
        """POST ``/repos/{owner}/{repo}/issues`` and return True on 201."""
        url = f"{endpoint.base_url.rstrip('/')}/repos/{owner}/{repo}/issues"
        headers = {
            **endpoint.auth.get_headers(),
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
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
                issue_number = response.json().get("number", "?")
                logger.info(
                    "GitHub issue #%s created in %s/%s for %s (%s)",
                    issue_number,
                    owner,
                    repo,
                    endpoint.endpoint_id,
                    context,
                )
                return True
            logger.warning(
                "GitHub issue creation returned %s for %s (%s): %s",
                response.status_code,
                endpoint.endpoint_id,
                context,
                response.text[:500],
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "GitHub issue creation failed for %s (%s): %s",
                endpoint.endpoint_id,
                context,
                exc,
            )
            return False

    @staticmethod
    def _format_event_body(event: NormalizedSecurityEvent) -> str:
        """Build a Markdown issue body for a security event."""
        lines = [
            f"## Security Event: {event.event_type}",
            "",
            f"**Severity:** {event.severity}",
            f"**Project:** {event.project_id}",
            f"**Timestamp:** {event.timestamp.isoformat()}",
            "",
            "### Summary",
            "",
            event.summary,
        ]

        if event.details:
            lines.append("")
            lines.append("### Details")
            lines.append("")
            for key, value in event.details.items():
                lines.append(f"- **{key}:** {value}")

        if event.finding_ids:
            lines.append("")
            lines.append("### Finding IDs")
            lines.append("")
            for fid in event.finding_ids:
                lines.append(f"- `{fid}`")

        lines.append("")
        lines.append("---")
        lines.append("*Created by PeaRL*")

        return "\n".join(lines)
