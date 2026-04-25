"""LiteLLM contract compliance client.

Queries LiteLLM's virtual key API to validate that an agent's runtime
behaviour matched its approved allowance profile contract.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class ContractCompliance(BaseModel):
    passed: bool
    violations: list[str]
    key_alias: str | None
    approved_models: list[str]
    actual_models_used: list[str]
    budget_cap_usd: float | None
    actual_spend_usd: float
    request_count: int
    checked_at: str = ""


class DriftReport(BaseModel):
    drifted: bool
    violations: list[str]
    agents_checked: int
    checked_at: str = ""
    model_drift: list[dict] = []
    permission_drift: list[dict] = []
    key_liveness: dict | None = None


class KeyDetails(BaseModel):
    """Parsed representation of a LiteLLM virtual key's full state."""
    key_alias: str | None = None
    team_id: str | None = None
    organization_id: str | None = None
    models: list[str] = []
    max_budget: float | None = None
    spend: float = 0.0
    soft_budget_cooldown: bool = False
    mcp_access_groups: list[str] = []
    blocked_tools: list[str] = []
    vector_stores: list[str] = []
    expires: str | None = None
    blocked: bool = False
    last_active: str | None = None
    rotation_count: int = 0
    last_rotation_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


_EXPIRY_WARNING_DAYS = 14


def check_key_lifecycle(
    key_alias: str,
    key_expiry_iso: str | None,
    key_rotation_days: int | None,
    now: "datetime | None" = None,
    last_rotation_at_iso: str | None = None,
) -> dict:
    """Compute key lifecycle compliance from stored policy values. No HTTP calls.

    Returns: key_alias, expires_at, days_until_expiry, rotation_overdue,
             days_since_last_rotation, violation, violation_reasons
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result: dict = {
        "key_alias": key_alias,
        "expires_at": key_expiry_iso,
        "days_until_expiry": None,
        "rotation_overdue": False,
        "days_since_last_rotation": None,
        "violation": False,
        "violation_reasons": [],
    }

    if key_expiry_iso:
        try:
            expiry = datetime.fromisoformat(key_expiry_iso.replace("Z", "+00:00"))
            delta = (expiry - now).total_seconds() / 86400
            result["days_until_expiry"] = round(delta, 1)
            if delta < _EXPIRY_WARNING_DAYS:
                result["violation"] = True
                if delta < 0:
                    result["violation_reasons"].append(
                        f"Key expired {abs(delta):.1f} days ago"
                    )
                else:
                    result["violation_reasons"].append(
                        f"Key expires in {delta:.1f} days (threshold: {_EXPIRY_WARNING_DAYS})"
                    )
        except ValueError:
            result["violation_reasons"].append(f"Cannot parse key_expiry: {key_expiry_iso!r}")

    if key_rotation_days and last_rotation_at_iso:
        try:
            last_rotation = datetime.fromisoformat(last_rotation_at_iso.replace("Z", "+00:00"))
            days_since = (now - last_rotation).total_seconds() / 86400
            result["days_since_last_rotation"] = round(days_since, 1)
            if days_since > key_rotation_days:
                result["rotation_overdue"] = True
                result["violation"] = True
                result["violation_reasons"].append(
                    f"Key not rotated in {days_since:.0f} days (required: every {key_rotation_days})"
                )
        except ValueError:
            pass

    return result


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

    async def _fetch_key_info(self, key_alias: str) -> dict:
        """Raw /key/info fetch. Raises on HTTP errors."""
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(
                f"{self._base_url}/key/info",
                params={"key_alias": key_alias},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def _fetch_compliance_data(self, key_alias: str) -> tuple[dict, list[dict]]:
        key_info = await self._fetch_key_info(key_alias)
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as http:
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

    async def get_key_details(self, key_alias: str) -> "KeyDetails | None":
        """Fetch full virtual key metadata. Returns None on 404 or connectivity error."""
        try:
            raw = await self._fetch_key_info(key_alias)
        except (httpx.ConnectError, httpx.HTTPStatusError):
            return None

        obj_perm: dict = raw.get("object_permission") or {}
        return KeyDetails(
            key_alias=raw.get("key_alias"),
            team_id=raw.get("team_id"),
            organization_id=raw.get("organization_id"),
            models=list(raw.get("models") or []),
            max_budget=raw.get("max_budget"),
            spend=float(raw.get("spend") or 0.0),
            soft_budget_cooldown=bool(raw.get("soft_budget_cooldown")),
            mcp_access_groups=list(obj_perm.get("mcp_access_groups") or []),
            blocked_tools=list(obj_perm.get("blocked_tools") or []),
            vector_stores=list(obj_perm.get("vector_stores") or []),
            expires=raw.get("expires"),
            blocked=bool(raw.get("blocked")),
            last_active=raw.get("last_active"),
            rotation_count=int(raw.get("rotation_count") or 0),
            last_rotation_at=raw.get("last_rotation_at"),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    async def get_agent(self, agent_id: str) -> dict | None:
        """Fetch a single agent from LiteLLM. Returns None if 404."""
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(
                f"{self._base_url}/v1/agents/{agent_id}",
                headers=headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def check_drift(self, snapshot: dict) -> DriftReport:
        """Compare stored contract snapshot against live LiteLLM state.

        When snapshot contains agent_contracts, fetches each key and checks:
          - model drift (model_allowlist vs live key.models)
          - permission drift (snapshot.mcp_allowlist vs live key.mcp_access_groups)
          - key liveness (blocked, expired)

        Falls back to legacy agent-ID + skill-hash check when agent_contracts absent.
        Degrades gracefully: LiteLLM unreachable → returns drifted=False with note.
        """
        checked_at = datetime.now(timezone.utc).isoformat()
        violations: list[str] = []
        model_drift: list[dict] = []
        permission_drift: list[dict] = []
        key_liveness: dict | None = None
        agents_checked = 0

        agent_contracts: list[dict] = snapshot.get("agent_contracts") or []
        mcp_allowlist: list[str] = list(snapshot.get("mcp_allowlist") or [])

        if agent_contracts:
            # New path: per-agent key pull
            for contract in agent_contracts:
                key_alias = contract.get("key_alias")
                if not key_alias:
                    continue

                try:
                    live_key = await self.get_key_details(key_alias)
                except Exception as exc:
                    violations.append(f"Key fetch failed for {key_alias!r}: {exc}")
                    continue

                if live_key is None:
                    violations.append(f"Key {key_alias!r} not found in LiteLLM — may have been deleted")
                    continue

                agents_checked += 1

                # Model drift
                approved_models: list[str] = contract.get("model_allowlist") or []
                if approved_models:
                    unauthorized = [m for m in live_key.models if m not in approved_models]
                    entry = {
                        "agent_id": contract.get("agent_id"),
                        "key_alias": key_alias,
                        "authorized_models": approved_models,
                        "live_models": live_key.models,
                        "unauthorized_models": unauthorized,
                        "violation": len(unauthorized) > 0,
                    }
                    model_drift.append(entry)
                    for m in unauthorized:
                        violations.append(
                            f"Model drift on {key_alias!r}: {m!r} not in approved contract {approved_models}"
                        )

                # Liveness
                if live_key.blocked:
                    key_liveness = {
                        "key_alias": key_alias,
                        "blocked": True,
                        "expires": live_key.expires,
                        "last_active": live_key.last_active,
                    }
                    violations.append(f"Key {key_alias!r} is blocked in LiteLLM")

                if live_key.expires:
                    try:
                        expiry = datetime.fromisoformat(live_key.expires.replace("Z", "+00:00"))
                        if expiry < datetime.now(timezone.utc):
                            violations.append(f"Key {key_alias!r} has expired: {live_key.expires}")
                            key_liveness = key_liveness or {}
                            key_liveness["expired"] = True
                    except ValueError:
                        pass

            # MCP permission drift (team-level)
            if mcp_allowlist and agent_contracts:
                first_alias = agent_contracts[0].get("key_alias")
                if first_alias:
                    try:
                        key = await self.get_key_details(first_alias)
                    except Exception:
                        key = None
                    if key:
                        unexpected_groups = [g for g in key.mcp_access_groups if g not in mcp_allowlist]
                        if unexpected_groups:
                            perm_entry = {
                                "key_alias": first_alias,
                                "approved_mcp": mcp_allowlist,
                                "live_mcp": key.mcp_access_groups,
                                "unexpected_groups": unexpected_groups,
                            }
                            permission_drift.append(perm_entry)
                            for g in unexpected_groups:
                                violations.append(
                                    f"MCP permission drift on {first_alias!r}: {g!r} not in approved allowlist"
                                )

        else:
            # Legacy path: check agent IDs exist + skill hash
            agent_ids: list[str] = snapshot.get("litellm_agent_ids") or []
            expected_hash: str | None = snapshot.get("skill_content_hash")

            for agent_id in agent_ids:
                try:
                    agent = await self.get_agent(agent_id)
                except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                    logger.warning("LiteLLM unreachable during drift check for agent %s: %s", agent_id, exc)
                    return DriftReport(
                        drifted=len(violations) > 0,
                        violations=violations + ["LiteLLM unreachable — drift check skipped"],
                        agents_checked=agents_checked,
                        checked_at=checked_at,
                    )

                agents_checked += 1
                if agent is None:
                    violations.append(f"Agent {agent_id!r} not found in LiteLLM")
                    continue

                if expected_hash:
                    live_hash = (
                        (agent.get("agent_card_params") or {}).get("skill_hash")
                        or (agent.get("agent_card_params") or {}).get("skills_hash")
                    )
                    if live_hash and live_hash != expected_hash:
                        violations.append(
                            f"Agent {agent_id!r} skill hash mismatch: "
                            f"snapshot={expected_hash!r} live={live_hash!r}"
                        )

        return DriftReport(
            drifted=len(violations) > 0,
            violations=violations,
            agents_checked=agents_checked,
            checked_at=checked_at,
            model_drift=model_drift,
            permission_drift=permission_drift,
            key_liveness=key_liveness,
        )
