"""Tests for Dark Factory governance container fields."""
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta, timezone


@pytest.fixture
def admin_token():
    """Generate a valid admin JWT for test requests."""
    import jwt as pyjwt
    from pearl.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "usr_test_admin",
        "roles": ["admin"],
        "scopes": ["*"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "type": "access",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
async def sample_project_id(app):
    """Create a minimal project and return its project_id."""
    from pearl.db.models.project import ProjectRow

    project_id = "proj_govtest_sample"
    session_factory = app.state.db_session_factory
    async with session_factory() as session:
        existing = await session.get(ProjectRow, project_id)
        if not existing:
            row = ProjectRow(
                project_id=project_id,
                name="Governance Test Project",
                owner_team="test-team",
                business_criticality="medium",
                external_exposure="internal",
                ai_enabled=True,
                schema_version="1.1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
    return project_id


@pytest.mark.asyncio
async def test_project_governance_state_endpoint_exists(app, admin_token):
    """GET /projects/{id}/governance-state returns 404 for missing project (not 405)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(
            "/api/v1/projects/proj_nonexistent/governance-state",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_register_agents_endpoint_exists(app, admin_token):
    """POST /projects/{id}/agents returns 404 for missing project (not 405)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/api/v1/projects/proj_nonexistent/agents",
            json={"coordinator": "agent_coord1", "workers": [], "evaluators": []},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_project_repo_update_governance_fields(app):
    """update_governance_fields sets Dark Factory fields on an existing project row."""
    from pearl.repositories.project_repo import ProjectRepository
    from pearl.db.models.project import ProjectRow

    project_id = "proj_repotest01"
    session_factory = app.state.db_session_factory

    async with session_factory() as session:
        existing = await session.get(ProjectRow, project_id)
        if not existing:
            row = ProjectRow(
                project_id=project_id,
                name="Repo Test",
                owner_team="test-team",
                business_criticality="medium",
                external_exposure="internal",
                ai_enabled=True,
                schema_version="1.1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()

    async with session_factory() as session:
        repo = ProjectRepository(session)
        updated = await repo.update_governance_fields(
            project_id=project_id,
            intake_card_id="card_001",
            goal_id="goal_abc",
            target_type="repo",
            target_id="repo:MASS-2.0",
            risk_classification="medium",
        )
        await session.commit()

        assert updated.intake_card_id == "card_001"
        assert updated.target_type == "repo"
        assert updated.target_id == "repo:MASS-2.0"
        assert updated.risk_classification == "medium"


@pytest.mark.asyncio
async def test_register_agents_on_project(app, admin_token, sample_project_id):
    """POST /projects/{id}/agents stores agent_members on the project."""
    payload = {
        "coordinator": "agent_coord_abc",
        "workers": ["agent_worker_1", "agent_worker_2"],
        "evaluators": ["agent_eval_1"],
        "litellm_key_refs": ["vk-worker-agent", "vk-governance-agent"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            f"/api/v1/projects/{sample_project_id}/agents",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_members"]["coordinator"] == "agent_coord_abc"
    assert len(data["agent_members"]["workers"]) == 2
    assert data["litellm_key_refs"] == ["vk-worker-agent", "vk-governance-agent"]


@pytest.mark.asyncio
async def test_governance_state_returns_project_context(app, admin_token, sample_project_id):
    """GET /projects/{id}/governance-state returns gates, approvals, and governance fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(
            f"/api/v1/projects/{sample_project_id}/governance-state",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "project_id" in data
    assert "pending_approvals" in data
    assert "gate_status" in data
    assert "agent_members" in data
    assert "goal_id" in data
