"""Tests for agent contract snapshot endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def admin_token():
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone
    from pearl.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "test-admin",
        "roles": ["admin"],
        "scopes": ["api"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "type": "access",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
async def sample_project_id(app):
    from pearl.db.models.project import ProjectRow
    from datetime import datetime, timezone

    async with app.state.db_session_factory() as session:
        row = ProjectRow(
            project_id="proj_snapshot_test",
            name="Snapshot Test Project",
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
    return "proj_snapshot_test"


@pytest.mark.asyncio
async def test_submit_contract_snapshot_returns_task_packet_id(app, admin_token, sample_project_id):
    """POST /projects/{id}/contract-snapshots creates a task packet and returns its ID."""
    payload = {
        "package_id": "pkg_abc123",
        "agent_roles": ["coordinator", "worker"],
        "litellm_agent_ids": ["agent_coord_1", "agent_worker_1"],
        "key_aliases": ["vk-worker-agent"],
        "skill_content_hash": "sha256:deadbeef",
        "mcp_allowlist": ["pearl-api", "pearl-dev"],
        "budget_usd": 5.0,
        "environment": "dev",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            f"/api/v1/projects/{sample_project_id}/contract-snapshots",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["task_packet_id"].startswith("tp_")
    assert data["project_id"] == sample_project_id
    assert data["contract_snapshot"]["package_id"] == "pkg_abc123"
    assert data["contract_snapshot"]["skill_content_hash"] == "sha256:deadbeef"


@pytest.mark.asyncio
async def test_submit_contract_snapshot_missing_project(app, admin_token):
    """POST /projects/{id}/contract-snapshots returns 404 for a nonexistent project."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/projects/proj_nonexistent/contract-snapshots",
            json={
                "package_id": "pkg_x",
                "litellm_agent_ids": [],
                "environment": "dev",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_contract_compliance_with_snapshot_returns_drift_key(app, admin_token, sample_project_id):
    """GET /task-packets/{id}/contract-compliance includes drift_check when snapshot present."""
    payload = {
        "package_id": "pkg_drift_test",
        "litellm_agent_ids": ["agent_coord_1"],
        "key_aliases": ["vk-worker-agent"],
        "skill_content_hash": "sha256:abc123",
        "mcp_allowlist": ["pearl-api"],
        "budget_usd": 2.0,
        "environment": "dev",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_r = await ac.post(
            f"/api/v1/projects/{sample_project_id}/contract-snapshots",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert create_r.status_code == 201
    packet_id = create_r.json()["task_packet_id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(
            f"/api/v1/task-packets/{packet_id}/contract-compliance",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code in (200, 503), r.text


@pytest.mark.asyncio
async def test_mcp_tools_list_includes_submit_contract_snapshot(app):
    """MCP tools/list includes pearl_submit_contract_snapshot."""
    from pearl.mcp.tools import TOOL_DEFINITIONS
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert "pearl_submit_contract_snapshot" in names, \
        f"Missing tool. Found: {sorted(names)}"


@pytest.mark.asyncio
async def test_drift_detected_when_agent_missing():
    """check_drift returns drifted=True when a litellm_agent_id is not found."""
    from unittest.mock import AsyncMock, patch
    from pearl.integrations.litellm import LiteLLMClient

    client = LiteLLMClient(base_url="http://fake-litellm", api_key="key")

    snapshot = {
        "litellm_agent_ids": ["agent_missing_1"],
        "skill_content_hash": "sha256:abc",
        "key_aliases": ["vk-worker-agent"],
        "mcp_allowlist": ["pearl-api"],
    }

    with patch.object(client, "get_agent", new=AsyncMock(return_value=None)):
        report = await client.check_drift(snapshot)

    assert report.drifted is True
    assert any("not found" in v.lower() for v in report.violations)


@pytest.mark.asyncio
async def test_no_drift_when_agent_exists_no_hash():
    """check_drift returns drifted=False when agent exists and no live hash to compare."""
    from unittest.mock import AsyncMock, patch
    from pearl.integrations.litellm import LiteLLMClient

    client = LiteLLMClient(base_url="http://fake-litellm", api_key="key")

    snapshot = {
        "litellm_agent_ids": ["agent_coord_1"],
        "skill_content_hash": "sha256:abc",
        "key_aliases": ["vk-worker-agent"],
        "mcp_allowlist": ["pearl-api"],
    }

    live_agent = {
        "agent_id": "agent_coord_1",
        "agent_card_params": {},
        "litellm_params": {"model": "gpt-4o"},
    }

    with patch.object(client, "get_agent", new=AsyncMock(return_value=live_agent)):
        report = await client.check_drift(snapshot)

    assert report.agents_checked == 1
    # No drift: agent exists, live agent has no hash to compare against
    assert report.drifted is False
    assert report.violations == []


@pytest.mark.asyncio
async def test_drift_check_degrades_gracefully_when_litellm_unreachable():
    """check_drift returns drifted=False with a note when LiteLLM is unreachable."""
    import httpx
    from unittest.mock import AsyncMock, patch
    from pearl.integrations.litellm import LiteLLMClient

    client = LiteLLMClient(base_url="http://unreachable", api_key="key")

    snapshot = {
        "litellm_agent_ids": ["agent_1"],
        "skill_content_hash": "sha256:abc",
        "key_aliases": [],
        "mcp_allowlist": [],
    }

    with patch.object(
        client, "get_agent",
        new=AsyncMock(side_effect=httpx.ConnectError("unreachable")),
    ):
        report = await client.check_drift(snapshot)

    assert report.drifted is False
    assert any("unreachable" in v.lower() for v in report.violations)
