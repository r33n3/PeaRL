"""Contract tests for SonarQube integration routes."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(client, project_id: str = "proj_sonar_test") -> str:
    """Create a minimal project for testing."""
    resp = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": project_id,
            "name": "Sonar Test Project",
            "description": "Contract test project",
            "owner_team": "engineering",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": False,
        },
    )
    # Accept 201 (created) or 409 (already exists from prior test)
    assert resp.status_code in (201, 409), f"Project create failed: {resp.status_code} {resp.text}"
    return project_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sonarqube_pull_no_integration_configured(client):
    """POST pull with no integration configured returns 404."""
    pid = await _create_project(client, "proj_sonar_pull_test")

    resp = await client.post(f"/api/v1/projects/{pid}/integrations/sonarqube/pull")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body or "error" in body or "message" in body


@pytest.mark.asyncio
async def test_sonarqube_status_no_integration(client):
    """GET status returns structured response even without integration configured."""
    pid = await _create_project(client, "proj_sonar_status_test")

    resp = await client.get(f"/api/v1/projects/{pid}/integrations/sonarqube/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "quality_gate" in body
    assert "metrics" in body
    assert "last_pull_at" in body
    assert body["integration_configured"] is False


@pytest.mark.asyncio
async def test_sonarqube_scan_invalid_path_traversal(client):
    """POST scan with path traversal attempt returns 400."""
    pid = await _create_project(client, "proj_sonar_scan_test")

    resp = await client.post(
        f"/api/v1/projects/{pid}/integrations/sonarqube/scan",
        json={"target_path": "../../etc/passwd"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sonarqube_scan_unregistered_path_returns_400(client):
    """POST scan with an unregistered (but valid) path returns 400."""
    pid = await _create_project(client, "proj_sonar_scan_unreg")

    resp = await client.post(
        f"/api/v1/projects/{pid}/integrations/sonarqube/scan",
        json={"target_path": "/tmp/some-random-unregistered-path"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sonarqube_pull_unknown_project_returns_404(client):
    """POST pull for a non-existent project returns 404."""
    resp = await client.post("/api/v1/projects/proj_does_not_exist/integrations/sonarqube/pull")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sonarqube_status_unknown_project_returns_404(client):
    """GET status for a non-existent project returns 404."""
    resp = await client.get("/api/v1/projects/proj_does_not_exist/integrations/sonarqube/status")
    assert resp.status_code == 404
