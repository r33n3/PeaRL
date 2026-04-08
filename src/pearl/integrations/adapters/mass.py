"""MASS 2.0 source adapter — tests connectivity and status via the MASS API."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = logging.getLogger(__name__)


class MassAdapter(SourceAdapter):
    """Adapter for MASS 2.0 AI deployment security scanner.

    MASS findings are ingested via the dedicated scan worker (mass_bridge.py),
    not via the pull-based adapter pattern.  This adapter exists solely to
    surface MASS in the integration catalogue and provide a connectivity test.

    Expected endpoint configuration:
        base_url:  e.g. ``http://host.docker.internal:80`` (or public MASS URL)
        auth:      Bearer token (``auth_type="bearer"``, ``raw_token=<api_key>``)
    """

    adapter_type = "mass"

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Verify MASS connectivity by listing recent scans (GET /scans?limit=1)."""
        base = endpoint.base_url.rstrip("/")
        headers: dict[str, str] = {}
        token = endpoint.auth.resolve_bearer_token() or endpoint.auth.resolve_api_key()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{base}/scans",
                params={"limit": 1},
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code in (200, 401, 403):
                # 401/403 means the server is reachable but credentials are wrong/missing —
                # still counts as "server is up" for a connectivity test.
                if resp.status_code == 200:
                    logger.info("MASS connection test succeeded for %s", endpoint.endpoint_id)
                    return True
                logger.warning(
                    "MASS reachable but returned HTTP %s for %s — check API key",
                    resp.status_code,
                    endpoint.endpoint_id,
                )
                return False
            logger.warning(
                "MASS connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("MASS connection test failed for %s: %s", endpoint.endpoint_id, exc)
            return False

    # ------------------------------------------------------------------
    # Pull findings — MASS uses the scan worker, not pull-based ingestion
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Not implemented — MASS findings are ingested via the scan worker."""
        logger.info(
            "MASS pull_findings called on %s — MASS uses scan worker, returning empty",
            endpoint.endpoint_id,
        )
        return []
