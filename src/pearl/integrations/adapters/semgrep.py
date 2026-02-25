"""Semgrep source adapter — pulls SAST findings from the Semgrep App API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "ERROR": "high",
    "WARNING": "moderate",
    "INFO": "low",
    "error": "high",
    "warning": "moderate",
    "info": "low",
    # Semgrep App may also return these forms
    "high": "high",
    "medium": "moderate",
    "moderate": "moderate",
    "low": "low",
    "critical": "critical",
}


class SemgrepAdapter(SourceAdapter):
    """Pulls SAST findings from the Semgrep App deployments API.

    Expected endpoint configuration:
        base_url:  e.g. ``https://semgrep.dev``
        auth:      Bearer token (``auth_type="bearer"``, ``bearer_token_env="SEMGREP_APP_TOKEN"``)
        labels:    ``{"deployment_slug": "<your-deployment>"}`` — defaults to ``"default"``
                   if not provided.
    """

    adapter_type: str = "semgrep"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify Semgrep App connectivity via ``GET /api/v1/deployments``."""
        url = f"{endpoint.base_url.rstrip('/')}/api/v1/deployments"
        headers = endpoint.auth.get_headers()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                logger.info("Semgrep connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "Semgrep connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Semgrep connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Pull findings
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull SAST findings from the Semgrep App deployments API.

        Calls ``GET /api/v1/deployments/{slug}/findings``.  The deployment
        slug is read from ``endpoint.labels["deployment_slug"]`` and falls
        back to ``"default"`` when the label is absent.
        """
        labels = endpoint.labels or {}
        slug = labels.get("deployment_slug", "default")
        url = f"{endpoint.base_url.rstrip('/')}/api/v1/deployments/{slug}/findings"
        headers = endpoint.auth.get_headers()
        params: dict[str, str] = {}
        if since is not None:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

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
                "Semgrep API returned HTTP %s when pulling findings for %s: %s",
                exc.response.status_code,
                endpoint.endpoint_id,
                exc,
            )
            return []
        except httpx.HTTPError as exc:
            logger.error(
                "HTTP error pulling Semgrep findings for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return []

        try:
            payload = resp.json()
        except ValueError:
            logger.error("Non-JSON response from Semgrep for %s", endpoint.endpoint_id)
            return []

        raw_findings: list[dict] = payload.get("findings", payload.get("results", []))

        findings: list[NormalizedFinding] = []
        for raw in raw_findings:
            try:
                finding = self._normalize_finding(raw)
                findings.append(finding)
            except Exception:
                logger.warning(
                    "Failed to normalize Semgrep finding %s — skipping",
                    raw.get("id", raw.get("ref", "<unknown>")),
                    exc_info=True,
                )

        logger.info(
            "Pulled %d Semgrep findings for endpoint %s",
            len(findings),
            endpoint.endpoint_id,
        )
        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_finding(raw: dict) -> NormalizedFinding:
        """Convert a single Semgrep finding dict to a *NormalizedFinding*."""
        # External ID — prefer explicit id, fall back to ref
        external_id = str(raw.get("id") or raw.get("ref", ""))

        # Title — use the rule name if available, otherwise the rule ID
        title = raw.get("rule_name") or raw.get("rule_id") or "Untitled Semgrep Finding"

        # Description
        description = raw.get("message") or raw.get("description")

        # Severity
        raw_severity = raw.get("severity", raw.get("level", "WARNING"))
        severity = _SEVERITY_MAP.get(str(raw_severity), "moderate")

        # Confidence
        confidence = raw.get("confidence")
        if confidence is not None:
            confidence = str(confidence).lower()

        # Affected components — the file path where the finding was detected
        path = raw.get("path") or raw.get("location", {}).get("path")
        affected_components = [path] if path else None

        # CWE IDs — may live under metadata.cwe or metadata.cwe_ids
        metadata: dict = raw.get("metadata", {})
        cwe_raw = metadata.get("cwe") or metadata.get("cwe_ids")
        if isinstance(cwe_raw, str):
            cwe_ids = [cwe_raw]
        elif isinstance(cwe_raw, list):
            cwe_ids = [str(c) for c in cwe_raw]
        else:
            cwe_ids = None

        # Category
        category = metadata.get("category", "security")

        # Detected timestamp
        detected_raw = raw.get("created_at") or raw.get("first_seen_at")
        if detected_raw:
            try:
                detected_at = datetime.fromisoformat(detected_raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return NormalizedFinding(
            external_id=external_id,
            source_tool="semgrep",
            source_type="sast",
            title=title,
            description=description,
            severity=severity,
            confidence=confidence,
            category=category,
            affected_components=affected_components,
            cwe_ids=cwe_ids,
            cve_id=None,
            cvss_score=None,
            fix_available=None,
            detected_at=detected_at,
            raw_record=raw,
        )
