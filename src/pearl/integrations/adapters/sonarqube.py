"""SonarQube source adapter — pulls SAST/quality findings via the SonarQube Web API."""

from __future__ import annotations

import structlog
from datetime import datetime, timezone

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = structlog.get_logger(__name__)

# SonarQube severity → PeaRL severity
_SEVERITY_MAP: dict[str, str] = {
    "BLOCKER": "critical",
    "CRITICAL": "high",
    "MAJOR": "moderate",
    "MINOR": "low",
    "INFO": "low",
}

# SonarQube type → PeaRL source_type
_TYPE_MAP: dict[str, str] = {
    "VULNERABILITY": "sast",
    "BUG": "sast",
    "CODE_SMELL": "sast",
    "SECURITY_HOTSPOT": "sast",
}


class SonarQubeAdapter(SourceAdapter):
    """Pulls SAST/quality findings from the SonarQube Web API.

    Expected endpoint configuration:
        base_url:  e.g. ``http://localhost:9090``
        auth:      Bearer token (``auth_type="bearer"``, ``bearer_token_env="SONAR_TOKEN"``)
        labels:    ``{"project_key": "<your-project-key>"}``
    """

    adapter_type: str = "sonarqube"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify SonarQube connectivity via ``GET /api/system/status``."""
        url = f"{endpoint.base_url.rstrip('/')}/api/system/status"
        headers = self._build_auth_headers(endpoint)
        try:
            client = await self._get_client()
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                logger.info("SonarQube connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "SonarQube connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("SonarQube connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Pull findings
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull issues from the SonarQube issues API.

        Calls ``GET /api/issues/search`` with ``componentKeys`` set to the
        project key from ``endpoint.labels["project_key"]``.
        """
        labels = endpoint.labels or {}
        project_key = labels.get("project_key", "")
        base = endpoint.base_url.rstrip("/")
        url = f"{base}/api/issues/search"
        headers = self._build_auth_headers(endpoint)

        params: dict[str, str | int] = {
            "componentKeys": project_key,
            "ps": 500,  # page size
            "p": 1,
        }
        if since is not None:
            params["createdAfter"] = since.strftime("%Y-%m-%dT%H:%M:%S%z")

        all_findings: list[NormalizedFinding] = []
        while True:
            try:
                client = await self._get_client()
                resp = await client.get(url, headers=headers, params=params, timeout=30.0)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "SonarQube API HTTP %s pulling findings for %s: %s",
                    exc.response.status_code,
                    endpoint.endpoint_id,
                    exc,
                )
                return all_findings
            except httpx.HTTPError as exc:
                logger.error(
                    "HTTP error pulling SonarQube findings for %s: %s",
                    endpoint.endpoint_id,
                    exc,
                )
                return all_findings

            try:
                payload = resp.json()
            except ValueError:
                logger.error("Non-JSON response from SonarQube for %s", endpoint.endpoint_id)
                return all_findings

            issues: list[dict] = payload.get("issues", [])
            for raw in issues:
                try:
                    finding = self._normalize_issue(raw)
                    all_findings.append(finding)
                except Exception:
                    logger.warning(
                        "Failed to normalize SonarQube issue %s — skipping",
                        raw.get("key", "<unknown>"),
                        exc_info=True,
                    )

            # Pagination
            total = payload.get("total", len(all_findings))
            page_size = int(params["ps"])
            page = int(params["p"])
            if page * page_size >= total:
                break
            params["p"] = page + 1

        logger.info(
            "Pulled %d SonarQube findings for endpoint %s",
            len(all_findings),
            endpoint.endpoint_id,
        )
        return all_findings

    # ------------------------------------------------------------------
    # Quality gate
    # ------------------------------------------------------------------

    async def get_quality_gate_status(
        self, endpoint: IntegrationEndpoint, project_key: str
    ) -> dict:
        """Fetch quality gate status for a project.

        Returns ``{"status": "OK"|"ERROR"|"WARN", "conditions": [...]}``.
        """
        base = endpoint.base_url.rstrip("/")
        url = f"{base}/api/qualitygates/project_status"
        headers = self._build_auth_headers(endpoint)
        params = {"projectKey": project_key}

        try:
            client = await self._get_client()
            resp = await client.get(url, headers=headers, params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            project_status = data.get("projectStatus", {})
            return {
                "status": project_status.get("status", "UNKNOWN"),
                "conditions": project_status.get("conditions", []),
            }
        except httpx.HTTPError as exc:
            logger.error(
                "Error fetching quality gate for %s/%s: %s",
                endpoint.endpoint_id,
                project_key,
                exc,
            )
            return {"status": "UNKNOWN", "conditions": []}

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def get_metrics(
        self, endpoint: IntegrationEndpoint, project_key: str
    ) -> dict:
        """Fetch key code-quality metrics for a project.

        Returns a dict of metric key → value for coverage, bugs,
        vulnerabilities, code_smells, security_hotspots, ncloc.
        """
        base = endpoint.base_url.rstrip("/")
        url = f"{base}/api/measures/component"
        headers = self._build_auth_headers(endpoint)
        metric_keys = "coverage,bugs,vulnerabilities,code_smells,security_hotspots,ncloc"
        params = {"component": project_key, "metricKeys": metric_keys}

        try:
            client = await self._get_client()
            resp = await client.get(url, headers=headers, params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            measures = data.get("component", {}).get("measures", [])
            return {m["metric"]: m.get("value") for m in measures}
        except httpx.HTTPError as exc:
            logger.error(
                "Error fetching metrics for %s/%s: %s",
                endpoint.endpoint_id,
                project_key,
                exc,
            )
            return {}

    # ------------------------------------------------------------------
    # Provision project
    # ------------------------------------------------------------------

    async def provision_project(
        self, endpoint: IntegrationEndpoint, project_key: str, project_name: str
    ) -> dict:
        """Create a project in SonarQube if it doesn't exist yet.

        Calls ``POST /api/projects/create``.
        Returns the API response dict.
        """
        base = endpoint.base_url.rstrip("/")
        url = f"{base}/api/projects/create"
        headers = self._build_auth_headers(endpoint)
        data = {"project": project_key, "name": project_name}

        try:
            client = await self._get_client()
            resp = await client.post(url, headers=headers, data=data, timeout=15.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            # 400 = project already exists — not an error in our context
            if exc.response.status_code == 400:
                logger.info(
                    "SonarQube project %s already exists for endpoint %s",
                    project_key,
                    endpoint.endpoint_id,
                )
                return {"project": {"key": project_key, "name": project_name}}
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_auth_headers(endpoint: IntegrationEndpoint) -> dict[str, str]:
        """Build auth headers — SonarQube accepts a Bearer token or Basic auth."""
        headers = endpoint.auth.get_headers()
        # SonarQube token-based auth: token as username with empty password (Basic)
        if not headers and endpoint.auth.auth_type == "none":
            pass  # No auth configured
        return headers

    @staticmethod
    def _normalize_issue(raw: dict) -> NormalizedFinding:
        """Convert a single SonarQube issue dict to a *NormalizedFinding*."""
        external_id = raw.get("key", "")
        title = raw.get("message") or raw.get("rule") or "Untitled SonarQube Issue"
        description = raw.get("message")

        raw_severity = raw.get("severity", "MAJOR")
        severity = _SEVERITY_MAP.get(str(raw_severity).upper(), "moderate")

        issue_type = raw.get("type", "CODE_SMELL")
        source_type = _TYPE_MAP.get(str(issue_type).upper(), "sast")

        # Affected component
        component = raw.get("component") or raw.get("project")
        affected_components = [component] if component else None

        # CWE IDs — may be in textRange or securityCategory
        # SonarQube encodes CWE in the rule's OWASP/CWE tags via cwe fields
        cwe_ids: list[str] | None = None
        security_standards = raw.get("securityStandards", [])
        cwe_list = [s for s in security_standards if s.startswith("cwe:")]
        if cwe_list:
            cwe_ids = [s.replace("cwe:", "CWE-") for s in cwe_list]

        # Detected timestamp
        creation_date = raw.get("creationDate")
        if creation_date:
            try:
                detected_at = datetime.fromisoformat(
                    creation_date.replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return NormalizedFinding(
            external_id=external_id,
            source_tool="sonarqube",
            source_type=source_type,
            title=title,
            description=description,
            severity=severity,
            confidence=None,
            category="security",
            affected_components=affected_components,
            cwe_ids=cwe_ids,
            cve_id=None,
            cvss_score=None,
            fix_available=None,
            detected_at=detected_at,
            raw_record=raw,
        )
