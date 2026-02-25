"""Tests for scan target API routes."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _create_project(client, project_id="proj_scan_test"):
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    await client.post("/api/v1/projects", json=project)
    return project_id


@pytest.mark.asyncio
async def test_register_scan_target(client):
    """Register a scan target for a project."""
    pid = await _create_project(client)
    body = {
        "repo_url": "https://github.com/org/repo",
        "tool_type": "mass",
        "branch": "main",
        "scan_frequency": "daily",
    }
    r = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["scan_target_id"].startswith("scnt_")
    assert data["project_id"] == pid
    assert data["repo_url"] == "https://github.com/org/repo"
    assert data["tool_type"] == "mass"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_scan_targets(client):
    """List scan targets for a project."""
    pid = await _create_project(client, "proj_st_list")
    body = {"repo_url": "https://github.com/org/repo1", "tool_type": "mass"}
    await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)

    r = await client.get(f"/api/v1/projects/{pid}/scan-targets")
    assert r.status_code == 200
    targets = r.json()
    assert len(targets) >= 1
    assert targets[0]["repo_url"] == "https://github.com/org/repo1"


@pytest.mark.asyncio
async def test_discovery_endpoint_filters_by_tool_type(client):
    """Discovery endpoint returns only targets matching tool_type."""
    pid = await _create_project(client, "proj_st_discover")
    # Register MASS and SAST targets
    await client.post(f"/api/v1/projects/{pid}/scan-targets", json={
        "repo_url": "https://github.com/org/repo-mass",
        "tool_type": "mass",
    })
    await client.post(f"/api/v1/projects/{pid}/scan-targets", json={
        "repo_url": "https://github.com/org/repo-sast",
        "tool_type": "sast",
    })

    # Discover MASS targets only
    r = await client.get("/api/v1/scan-targets", params={"tool_type": "mass"})
    assert r.status_code == 200
    targets = r.json()
    mass_urls = [t["repo_url"] for t in targets]
    assert "https://github.com/org/repo-mass" in mass_urls
    # SAST target should not appear in MASS discovery
    assert "https://github.com/org/repo-sast" not in mass_urls


@pytest.mark.asyncio
async def test_heartbeat_updates_last_scanned(client):
    """Heartbeat updates last_scanned_at and last_scan_status."""
    pid = await _create_project(client, "proj_st_hb")
    body = {"repo_url": "https://github.com/org/repo-hb", "tool_type": "mass"}
    create_r = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    stid = create_r.json()["scan_target_id"]

    hb = {
        "status": "succeeded",
        "scanned_at": "2026-02-20T10:00:00Z",
    }
    r = await client.post(f"/api/v1/scan-targets/{stid}/heartbeat", json=hb)
    assert r.status_code == 200
    data = r.json()
    assert data["last_scan_status"] == "succeeded"
    assert data["last_scanned_at"] is not None


@pytest.mark.asyncio
async def test_duplicate_natural_key_returns_error(client):
    """Duplicate (project_id, repo_url, tool_type, branch) returns error."""
    pid = await _create_project(client, "proj_st_dup")
    body = {"repo_url": "https://github.com/org/repo-dup", "tool_type": "mass"}
    r1 = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    assert r1.status_code == 201

    r2 = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_soft_delete_sets_disabled(client):
    """DELETE sets status to disabled (soft delete)."""
    pid = await _create_project(client, "proj_st_del")
    body = {"repo_url": "https://github.com/org/repo-del", "tool_type": "mass"}
    create_r = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    stid = create_r.json()["scan_target_id"]

    r = await client.delete(f"/api/v1/projects/{pid}/scan-targets/{stid}")
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_discovery_returns_only_active(client):
    """Discovery endpoint only returns active targets, not disabled ones."""
    pid = await _create_project(client, "proj_st_active")

    # Create and disable one
    body = {"repo_url": "https://github.com/org/disabled-repo", "tool_type": "mass"}
    create_r = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    stid = create_r.json()["scan_target_id"]
    await client.delete(f"/api/v1/projects/{pid}/scan-targets/{stid}")

    # Create an active one
    body2 = {"repo_url": "https://github.com/org/active-repo", "tool_type": "mass"}
    await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body2)

    r = await client.get("/api/v1/scan-targets", params={"tool_type": "mass"})
    urls = [t["repo_url"] for t in r.json()]
    assert "https://github.com/org/active-repo" in urls
    assert "https://github.com/org/disabled-repo" not in urls


@pytest.mark.asyncio
async def test_update_scan_target(client):
    """Update scan target configuration."""
    pid = await _create_project(client, "proj_st_upd")
    body = {"repo_url": "https://github.com/org/repo-upd", "tool_type": "mass"}
    create_r = await client.post(f"/api/v1/projects/{pid}/scan-targets", json=body)
    stid = create_r.json()["scan_target_id"]

    r = await client.put(
        f"/api/v1/projects/{pid}/scan-targets/{stid}",
        json={"branch": "develop", "scan_frequency": "hourly"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["branch"] == "develop"
    assert data["scan_frequency"] == "hourly"
