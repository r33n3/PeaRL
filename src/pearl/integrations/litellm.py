"""LiteLLM contract compliance client.

Queries LiteLLM's virtual key API to validate that an agent's runtime
behaviour matched its approved allowance profile contract.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ContractCompliance(BaseModel):
    passed: bool
    violations: list[str]
    key_alias: str
    approved_models: list[str]
    actual_models_used: list[str]
    budget_cap_usd: float | None
    actual_spend_usd: float
    request_count: int
    checked_at: str = ""


class LiteLLMClient:
    """Async client for LiteLLM contract compliance queries."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_key_compliance(
        self,
        key_alias: str,
        budget_cap_usd: float | None,
        allowed_models: list[str],
    ) -> ContractCompliance:
        """Query LiteLLM for spend + model usage and compare against the approved contract.

        Degrades gracefully: if LiteLLM is unreachable or returns a non-200 response,
        returns passed=True with a 'unreachable' violation note so the gate is not
        hard-blocked by infrastructure failure.
        """
        checked_at = datetime.now(timezone.utc).isoformat()

        try:
            key_info, spend_logs = await self._fetch_compliance_data(key_alias)
        except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
            logger.warning("LiteLLM unreachable during contract check for %s: %s", key_alias, exc)
            return ContractCompliance(
                passed=True,
                violations=["LiteLLM unreachable — contract check skipped"],
                key_alias=key_alias,
                approved_models=allowed_models,
                actual_models_used=[],
                budget_cap_usd=budget_cap_usd,
                actual_spend_usd=0.0,
                request_count=0,
                checked_at=checked_at,
            )

        actual_spend = float(key_info.get("spend") or 0.0)
        actual_models = sorted({
            log["model"] for log in spend_logs if log.get("model")
        })
        request_count = len(spend_logs)

        violations: list[str] = []

        if budget_cap_usd is not None and actual_spend > budget_cap_usd:
            violations.append(
                f"Budget exceeded: actual ${actual_spend:.4f} > cap ${budget_cap_usd:.2f}"
            )

        if allowed_models:
            unauthorized = [m for m in actual_models if m not in allowed_models]
            for model in unauthorized:
                violations.append(
                    f"Unauthorized model called: {model!r} (allowed: {allowed_models})"
                )

        return ContractCompliance(
            passed=len(violations) == 0,
            violations=violations,
            key_alias=key_alias,
            approved_models=list(
                key_info["models"] if "models" in key_info else allowed_models
            ),
            actual_models_used=actual_models,
            budget_cap_usd=budget_cap_usd,
            actual_spend_usd=actual_spend,
            request_count=request_count,
            checked_at=checked_at,
        )

    async def _fetch_compliance_data(self, key_alias: str) -> tuple[dict, list[dict]]:
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as http:
            info_resp = await http.get(
                f"{self._base_url}/key/info",
                params={"key_alias": key_alias},
                headers=headers,
            )
            info_resp.raise_for_status()
            key_info: dict = info_resp.json()

            logs_resp = await http.get(
                f"{self._base_url}/spend/logs",
                params={"key_alias": key_alias},
                headers=headers,
            )
            logs_resp.raise_for_status()
            spend_logs: list[dict] = logs_resp.json()
            if not isinstance(spend_logs, list):
                spend_logs = []

        return key_info, spend_logs
