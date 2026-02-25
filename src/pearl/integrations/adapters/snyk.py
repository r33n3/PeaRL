"""Snyk source adapter — pulls SCA findings from the Snyk API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "medium": "moderate",
    "low": "low",
}


class SnykAdapter(SourceAdapter):
    """Pulls SCA vulnerability findings from the Snyk reporting API.

    Expected endpoint configuration:
        base_url:  e.g. ``https://api.snyk.io``
        auth:      Bearer token (``auth_type="bearer"``, ``bearer_token_env="SNYK_TOKEN"``)
        labels:    Optional ``{"org_id": "..."}`` for org-scoped queries.
    """

    adapter_type: str = "snyk"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify Snyk API connectivity by hitting the ``/v1/user`` endpoint."""
        url = f"{endpoint.base_url.rstrip('/')}/v1/user"
        headers = endpoint.auth.get_headers()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                logger.info("Snyk connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "Snyk connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Snyk connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Pull findings
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull the latest issues from the Snyk reporting API.

        Uses ``GET /v1/reporting/issues/latest`` which returns a flat list of
        issues across all monitored projects for the authenticated account.

        If *endpoint.project_mapping* is provided, only findings whose Snyk
        project ID appears as a key in the mapping are included.
        """
        url = f"{endpoint.base_url.rstrip('/')}/v1/reporting/issues/latest"
        headers = endpoint.auth.get_headers()
        params: dict[str, str] = {}
        if since is not None:
            params["from"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Snyk API returned HTTP %s when pulling findings for %s: %s",
                exc.response.status_code,
                endpoint.endpoint_id,
                exc,
            )
            return []
        except httpx.HTTPError as exc:
            logger.error(
                "HTTP error pulling Snyk findings for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return []

        try:
            payload = resp.json()
        except ValueError:
            logger.error("Non-JSON response from Snyk for %s", endpoint.endpoint_id)
            return []

        raw_issues: list[dict] = payload.get("results", payload.get("issues", []))
        allowed_projects: set[str] | None = None
        if endpoint.project_mapping:
            allowed_projects = set(endpoint.project_mapping.keys())

        findings: list[NormalizedFinding] = []
        for issue in raw_issues:
            try:
                finding = self._normalize_issue(issue, allowed_projects)
                if finding is not None:
                    findings.append(finding)
            except Exception:
                logger.warning(
                    "Failed to normalize Snyk issue %s — skipping",
                    issue.get("id", "<unknown>"),
                    exc_info=True,
                )

        logger.info(
            "Pulled %d Snyk findings for endpoint %s",
            len(findings),
            endpoint.endpoint_id,
        )
        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_issue(
        issue: dict,
        allowed_projects: set[str] | None,
    ) -> NormalizedFinding | None:
        """Convert a single Snyk issue dict to a *NormalizedFinding*.

        Returns ``None`` if the issue belongs to a project not in
        *allowed_projects* (when the filter is active).
        """
        project_id = issue.get("projectId") or issue.get("project", {}).get("id")
        if allowed_projects is not None and project_id not in allowed_projects:
            return None

        issue_data: dict = issue.get("issueData", {})

        # Severity
        raw_severity = (issue_data.get("severity") or "low").lower()
        severity = _SEVERITY_MAP.get(raw_severity, "low")

        # Identifiers
        identifiers: dict = issue_data.get("identifiers", {})
        cwe_raw = identifiers.get("CWE", [])
        cwe_ids = [str(c) for c in cwe_raw] if cwe_raw else None

        cve_raw = identifiers.get("CVE", [])
        cve_id = str(cve_raw[0]) if cve_raw else None

        # Affected component
        pkg_name = issue.get("pkgName") or issue_data.get("packageName")
        affected_components = [pkg_name] if pkg_name else None

        # CVSS
        cvss_score: float | None = None
        raw_cvss = issue_data.get("cvssScore")
        if raw_cvss is not None:
            try:
                cvss_score = float(raw_cvss)
            except (TypeError, ValueError):
                cvss_score = None

        # Fix available
        fix_available: bool | None = None
        if issue_data.get("isUpgradable") or issue_data.get("isPatchable"):
            fix_available = True
        elif "isUpgradable" in issue_data:
            fix_available = False

        # Detected timestamp
        detected_raw = issue.get("introducedDate") or issue_data.get("publicationTime")
        if detected_raw:
            try:
                detected_at = datetime.fromisoformat(detected_raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return NormalizedFinding(
            external_id=str(issue.get("id", "")),
            source_tool="snyk",
            source_type="sca",
            title=issue_data.get("title", "Untitled Snyk Issue"),
            description=issue_data.get("description"),
            severity=severity,
            confidence=None,
            category="security",
            affected_components=affected_components,
            cwe_ids=cwe_ids,
            cve_id=cve_id,
            cvss_score=cvss_score,
            fix_available=fix_available,
            detected_at=detected_at,
            raw_record=issue,
        )
