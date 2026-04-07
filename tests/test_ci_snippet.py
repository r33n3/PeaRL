"""Tests for the CI snippet route.

GET /api/v1/projects/{project_id}/ci-snippet returns a platform-appropriate
CI YAML snippet for a project. These tests cover the GitHub Actions default
path and the 404 case.
"""

import pytest

from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(db_session, project_id: str | None = None) -> str:
    """Insert a minimal project row and flush. Returns the project_id."""
    pid = project_id or generate_id("proj")
    repo = ProjectRepository(db_session)
    await repo.create(
        project_id=pid,
        name="Test Project",
        description="test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=False,
    )
    await db_session.commit()
    return pid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ci_snippet_returns_github_actions_by_default(client, db_session):
    """GET returns 200 with platform=github_actions (no Azure DevOps integration)."""
    pid = await _create_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/ci-snippet")

    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "github_actions"
    assert "project_id" in data
    assert "snippet" in data
    assert "instructions" in data


@pytest.mark.anyio
async def test_ci_snippet_contains_project_id(client, db_session):
    """The project_id string appears inside the returned snippet YAML."""
    pid = await _create_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/ci-snippet")

    assert resp.status_code == 200
    snippet = resp.json()["snippet"]
    assert pid in snippet


@pytest.mark.anyio
async def test_ci_snippet_contains_two_jobs(client, db_session):
    """Snippet has both the scan: and gate: jobs plus required keywords."""
    pid = await _create_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/ci-snippet")

    assert resp.status_code == 200
    snippet = resp.json()["snippet"]
    assert "jobs:" in snippet
    assert "scan:" in snippet
    assert "gate:" in snippet
    assert "PEARL_SCAN_ENABLED" in snippet
    assert "promotions/evaluate" in snippet


@pytest.mark.anyio
async def test_ci_snippet_404_for_unknown_project(client):
    """Non-existent project returns 404."""
    resp = await client.get("/api/v1/projects/proj_doesnotexist/ci-snippet")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_ci_snippet_instructions_count(client, db_session):
    """GitHub Actions path returns exactly 5 instruction items."""
    pid = await _create_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/ci-snippet")

    assert resp.status_code == 200
    instructions = resp.json()["instructions"]
    assert len(instructions) == 5
