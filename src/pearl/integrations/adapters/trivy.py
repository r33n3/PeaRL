"""Trivy source adapter — pulls container-scan findings from a Trivy Server instance."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "moderate",
    "LOW": "low",
    "UNKNOWN": "low",
    # Lower-case variants for convenience
    "critical": "critical",
    "high": "high",
    "medium": "moderate",
    "low": "low",
    "unknown": "low",
}


class TrivyAdapter(SourceAdapter):
    """Pulls container-scan vulnerability findings from a Trivy Server.

    Trivy Server exposes a REST API that can scan images on demand or serve
    cached reports.  This adapter supports two operational modes:

    1. **Report mode** — fetches the latest cached report via
       ``GET /api/v1/reports/latest`` (default).
    2. **Scan mode** — triggers a scan via ``GET /v1/scan`` (used when the
       ``scan_mode`` label is set to ``"on_demand"``).

    Expected endpoint configuration:
        base_url:  e.g. ``http://trivy-server:4954``
        auth:      Optional token header (``auth_type="bearer"`` or ``"api_key"``).
        labels:    ``{"scan_mode": "on_demand"}`` to use the scan endpoint
                   instead of the report endpoint.
    """

    adapter_type: str = "trivy"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify Trivy Server health via ``GET /healthz``."""
        url = f"{endpoint.base_url.rstrip('/')}/healthz"
        headers = endpoint.auth.get_headers()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                logger.info("Trivy connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "Trivy connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("Trivy connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Pull findings
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull vulnerability findings from Trivy Server.

        By default the adapter fetches the latest cached report from
        ``GET /api/v1/reports/latest``.  When the endpoint label
        ``scan_mode`` is set to ``"on_demand"``, the ``GET /v1/scan``
        endpoint is used instead.
        """
        labels = endpoint.labels or {}
        scan_mode = labels.get("scan_mode", "report")

        if scan_mode == "on_demand":
            url = f"{endpoint.base_url.rstrip('/')}/v1/scan"
        else:
            url = f"{endpoint.base_url.rstrip('/')}/api/v1/reports/latest"

        headers = endpoint.auth.get_headers()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=60.0)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Trivy API returned HTTP %s when pulling findings for %s: %s",
                exc.response.status_code,
                endpoint.endpoint_id,
                exc,
            )
            return []
        except httpx.HTTPError as exc:
            logger.error(
                "HTTP error pulling Trivy findings for %s: %s",
                endpoint.endpoint_id,
                exc,
            )
            return []

        try:
            payload = resp.json()
        except ValueError:
            logger.error("Non-JSON response from Trivy for %s", endpoint.endpoint_id)
            return []

        # Trivy JSON reports contain a top-level "Results" array.  Each
        # result has a "Target" (image layer / file) and "Vulnerabilities".
        results: list[dict] = payload.get("Results", payload.get("results", []))

        findings: list[NormalizedFinding] = []
        for result in results:
            target = result.get("Target", result.get("target", "unknown"))
            vulnerabilities: list[dict] = result.get(
                "Vulnerabilities", result.get("vulnerabilities", [])
            ) or []
            for vuln in vulnerabilities:
                try:
                    finding = self._normalize_vulnerability(vuln, target, since)
                    if finding is not None:
                        findings.append(finding)
                except Exception:
                    logger.warning(
                        "Failed to normalize Trivy vulnerability %s — skipping",
                        vuln.get("VulnerabilityID", "<unknown>"),
                        exc_info=True,
                    )

        logger.info(
            "Pulled %d Trivy findings for endpoint %s",
            len(findings),
            endpoint.endpoint_id,
        )
        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_vulnerability(
        vuln: dict,
        target: str,
        since: datetime | None,
    ) -> NormalizedFinding | None:
        """Convert a single Trivy vulnerability dict to a *NormalizedFinding*.

        Returns ``None`` if the vulnerability was published before *since*
        (when the filter is active).
        """
        # Detected / published timestamp
        detected_raw = (
            vuln.get("PublishedDate")
            or vuln.get("publishedDate")
            or vuln.get("LastModifiedDate")
        )
        if detected_raw:
            try:
                detected_at = datetime.fromisoformat(detected_raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        if since is not None and detected_at < since:
            return None

        # External ID / CVE
        vuln_id = vuln.get("VulnerabilityID") or vuln.get("vulnerabilityID", "")
        cve_id = vuln_id if vuln_id.upper().startswith("CVE-") else None

        # Title
        title = vuln.get("Title") or vuln.get("title") or vuln_id or "Untitled Trivy Vulnerability"

        # Description
        description = vuln.get("Description") or vuln.get("description")

        # Severity
        raw_severity = vuln.get("Severity") or vuln.get("severity", "UNKNOWN")
        severity = _SEVERITY_MAP.get(str(raw_severity), "low")

        # CVSS score — try multiple nested paths
        cvss_score: float | None = None
        cvss_block = vuln.get("CVSS") or vuln.get("cvss") or {}
        for source_key in ("nvd", "redhat", "ghsa"):
            source_data = cvss_block.get(source_key, {})
            score = source_data.get("V3Score") or source_data.get("v3Score")
            if score is not None:
                try:
                    cvss_score = float(score)
                except (TypeError, ValueError):
                    continue
                break

        # Affected component
        pkg_name = vuln.get("PkgName") or vuln.get("pkgName")
        installed_version = vuln.get("InstalledVersion") or vuln.get("installedVersion")
        if pkg_name:
            component = f"{pkg_name}@{installed_version}" if installed_version else pkg_name
            affected_components = [component]
        else:
            affected_components = [target] if target != "unknown" else None

        # Fix available
        fixed_version = vuln.get("FixedVersion") or vuln.get("fixedVersion")
        fix_available = bool(fixed_version) if fixed_version is not None else None

        # CWE IDs
        cwe_raw = vuln.get("CweIDs") or vuln.get("cweIDs") or vuln.get("cwe_ids")
        if isinstance(cwe_raw, list):
            cwe_ids = [str(c) for c in cwe_raw] if cwe_raw else None
        else:
            cwe_ids = None

        return NormalizedFinding(
            external_id=str(vuln_id),
            source_tool="trivy",
            source_type="container_scan",
            title=title,
            description=description,
            severity=severity,
            confidence=None,
            category="security",
            affected_components=affected_components,
            cwe_ids=cwe_ids,
            cve_id=cve_id,
            cvss_score=cvss_score,
            fix_available=fix_available,
            detected_at=detected_at,
            raw_record=vuln,
        )
