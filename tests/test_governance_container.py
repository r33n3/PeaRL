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
