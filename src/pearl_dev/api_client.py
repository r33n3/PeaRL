"""Lightweight HTTP client for pearl-dev sync to communicate with PeaRL API."""

from __future__ import annotations

import httpx


class PearlAPIClient:
    """Sync HTTP client for pearl-dev CLI commands."""

    def __init__(self, base_url: str = "http://localhost:8080/api/v1") -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, body: dict | None = None, timeout: float = 30.0) -> httpx.Response | None:
        """POST helper with error handling."""
        try:
            return httpx.post(f"{self.base_url}{path}", json=body, timeout=timeout)
        except httpx.HTTPError:
            return None

    def _get(self, path: str, timeout: float = 30.0) -> httpx.Response | None:
        """GET helper with error handling."""
        try:
            return httpx.get(f"{self.base_url}{path}", timeout=timeout)
        except httpx.HTTPError:
            return None

    def get_compiled_package(self, project_id: str) -> dict | None:
        """Fetch the latest compiled context package for a project."""
        r = self._get(f"/projects/{project_id}/compiled-package")
        if r and r.status_code == 200:
            return r.json()
        return None

    def get_promotion_readiness(self, project_id: str) -> dict | None:
        """Fetch the latest promotion readiness evaluation."""
        r = self._get(f"/projects/{project_id}/promotions/readiness")
        if r and r.status_code == 200:
            data = r.json()
            if data.get("status") == "no_evaluation":
                return None
            return data
        return None

    def request_promotion(self, project_id: str) -> dict | None:
        """Request promotion for a project."""
        r = self._post(f"/projects/{project_id}/promotions/request")
        if r and r.status_code in (200, 202):
            return r.json()
        return None

    def get_scan_targets(self, project_id: str) -> list[dict] | None:
        """Fetch scan targets for a project."""
        r = self._get(f"/projects/{project_id}/scan-targets")
        if r and r.status_code == 200:
            return r.json()
        return None

    def register_scan_target(
        self,
        project_id: str,
        repo_url: str,
        tool_type: str = "mass",
        branch: str = "main",
        scan_frequency: str = "daily",
    ) -> dict | None:
        """Register a repo as a scan target for a project."""
        r = self._post(
            f"/projects/{project_id}/scan-targets",
            {
                "repo_url": repo_url,
                "tool_type": tool_type,
                "branch": branch,
                "scan_frequency": scan_frequency,
            },
        )
        if r and r.status_code == 201:
            return r.json()
        return None

    def register_project(
        self,
        project_id: str,
        name: str | None = None,
        environment: str = "dev",
        ai_enabled: bool = True,
        business_criticality: str = "moderate",
    ) -> dict | None:
        """Register a project in PeaRL API."""
        r = self._post(
            "/projects",
            {
                "schema_version": "1.1",
                "project_id": project_id,
                "name": name or project_id.removeprefix("proj_"),
                "owner_team": "default",
                "business_criticality": business_criticality,
                "external_exposure": "internal_only",
                "ai_enabled": ai_enabled,
            },
        )
        if r and r.status_code in (200, 201):
            return r.json()
        return None

    def upsert_org_baseline(self, project_id: str, baseline: dict) -> dict | None:
        """Upsert org baseline for a project."""
        r = self._post(f"/projects/{project_id}/org-baseline", baseline)
        if r and r.status_code in (200, 201):
            return r.json()
        return None

    def upsert_app_spec(self, project_id: str, spec: dict) -> dict | None:
        """Upsert application spec for a project."""
        r = self._post(f"/projects/{project_id}/app-spec", spec)
        if r and r.status_code in (200, 201):
            return r.json()
        return None

    def upsert_env_profile(self, project_id: str, profile: dict) -> dict | None:
        """Upsert environment profile for a project."""
        r = self._post(f"/projects/{project_id}/environment-profile", profile)
        if r and r.status_code in (200, 201):
            return r.json()
        return None

    def push_audit_events(self, project_id: str, events: list[dict]) -> dict | None:
        """Push local audit events to the PeaRL API."""
        r = self._post(
            f"/projects/{project_id}/audit-events",
            {"events": events},
            timeout=60.0,
        )
        if r and r.status_code == 201:
            return r.json()
        return None

    def push_governance_costs(self, project_id: str, entries: list[dict]) -> dict | None:
        """Push local cost ledger entries to the PeaRL API."""
        r = self._post(
            f"/projects/{project_id}/governance-costs",
            {"entries": entries},
            timeout=60.0,
        )
        if r and r.status_code == 201:
            return r.json()
        return None

    # --- Integration endpoints ---

    def list_integrations(self, project_id: str) -> list[dict] | None:
        """List configured integration endpoints for a project."""
        r = self._get(f"/projects/{project_id}/integrations")
        if r and r.status_code == 200:
            return r.json()
        return None

    def register_integration(self, project_id: str, config: dict) -> dict | None:
        """Register a new integration endpoint."""
        r = self._post(f"/projects/{project_id}/integrations", config)
        if r and r.status_code == 201:
            return r.json()
        return None

    def test_integration(self, project_id: str, endpoint_id: str) -> dict | None:
        """Test connectivity to an integration endpoint."""
        r = self._post(f"/projects/{project_id}/integrations/{endpoint_id}/test")
        if r and r.status_code == 200:
            return r.json()
        return None

    def pull_integration(self, project_id: str, endpoint_id: str) -> dict | None:
        """Trigger a pull from a source integration endpoint."""
        r = self._post(f"/projects/{project_id}/integrations/{endpoint_id}/pull")
        if r and r.status_code == 200:
            return r.json()
        return None

    def disable_integration(self, project_id: str, endpoint_id: str) -> dict | None:
        """Disable an integration endpoint."""
        try:
            r = httpx.delete(
                f"{self.base_url}/projects/{project_id}/integrations/{endpoint_id}",
                timeout=30.0,
            )
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        return None

    def compile_context(self, project_id: str) -> dict | None:
        """Trigger context compilation for a project."""
        r = self._post(
            f"/projects/{project_id}/compile-context",
            {
                "schema_version": "1.1",
                "project_id": project_id,
                "compile_options": {},
                "trace_id": "pearl_dev_init",
            },
        )
        if r and r.status_code in (200, 202):
            return r.json()
        return None
