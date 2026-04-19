"""LiteLLM source adapter — pulls compliance violations as PeaRL findings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from pearl.integrations.adapters.base import SourceAdapter
from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import NormalizedFinding

logger = logging.getLogger(__name__)


class LiteLLMAdapter(SourceAdapter):
    """Adapter for LiteLLM AI gateway.

    Pulls spend and model compliance violations for a set of virtual key aliases
    and converts them to NormalizedFindings.

    Expected endpoint configuration:
        base_url:      LiteLLM proxy URL (e.g. ``http://localhost:4000``)
        auth:          Bearer token (``auth_type="bearer"``, ``raw_token=<master_key>``)
        labels:        ``{"key_aliases": "alias1,alias2,alias3"}``
    """

    adapter_type = "litellm"

    # ------------------------------------------------------------------
    # Pull findings
    # ------------------------------------------------------------------

    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull compliance violations as findings.

        Reads key_aliases from endpoint.labels (comma-separated string).
        For each alias, calls LiteLLMClient.get_key_compliance().
        Converts violations to NormalizedFinding with:
          - category="governance"
          - severity mapping: "budget" in violation → "high",
                              "model" in violation → "medium", default → "high"
          - source_tool="litellm"
          - external_id=f"litellm-{key_alias}-{idx}"
          - title=violation text
          - description=f"LiteLLM compliance violation for key alias: {key_alias}"

        If LiteLLM is unreachable (ConnectError/HTTPStatusError), returns []
        (fail-open — gateway downtime should not block governance workflows).
        """
        from pearl.integrations.litellm import LiteLLMClient

        api_key = endpoint.auth.resolve_bearer_token() or ""
        client = LiteLLMClient(base_url=endpoint.base_url, api_key=api_key)

        labels: dict[str, str] = endpoint.labels or {}
        raw_aliases = labels.get("key_aliases", "")
        key_aliases = [a.strip() for a in raw_aliases.split(",") if a.strip()]

        findings: list[NormalizedFinding] = []
        now = datetime.now(timezone.utc)

        for key_alias in key_aliases:
            try:
                compliance = await client.get_key_compliance(
                    key_alias=key_alias,
                    budget_cap_usd=None,
                    allowed_models=[],
                )
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                logger.warning(
                    "LiteLLM unreachable during pull_findings for alias %s on %s: %s",
                    key_alias,
                    endpoint.endpoint_id,
                    exc,
                )
                continue

            for idx, violation in enumerate(compliance.violations):
                violation_lower = violation.lower()
                if "budget" in violation_lower:
                    severity = "high"
                elif "model" in violation_lower:
                    severity = "medium"
                else:
                    severity = "high"

                findings.append(
                    NormalizedFinding(
                        external_id=f"litellm-{key_alias}-{idx}",
                        source_tool="litellm",
                        source_type="governance",
                        title=violation,
                        description=f"LiteLLM compliance violation for key alias: {key_alias}",
                        severity=severity,
                        category="governance",
                        detected_at=now,
                        raw_record={
                            "key_alias": key_alias,
                            "violation_index": idx,
                            "actual_spend_usd": compliance.actual_spend_usd,
                            "budget_cap_usd": compliance.budget_cap_usd,
                            "actual_models_used": compliance.actual_models_used,
                            "approved_models": compliance.approved_models,
                            "request_count": compliance.request_count,
                            "checked_at": compliance.checked_at,
                        },
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """GET {endpoint.base_url}/health/liveliness — return True if 200."""
        base = endpoint.base_url.rstrip("/")
        try:
            headers = endpoint.auth.get_headers()
            client = await self._get_client()
            resp = await client.get(f"{base}/health/liveliness", headers=headers, timeout=10.0)
            if resp.status_code == 200:
                logger.info("LiteLLM connection test succeeded for %s", endpoint.endpoint_id)
                return True
            logger.warning(
                "LiteLLM connection test returned HTTP %s for %s",
                resp.status_code,
                endpoint.endpoint_id,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "LiteLLM connection test failed for %s: %s", endpoint.endpoint_id, exc
            )
            return False
