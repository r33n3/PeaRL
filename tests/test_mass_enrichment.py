"""Tests for MassClient enrichment methods."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from pearl.scanning.mass_bridge import MassClient


@pytest.mark.asyncio
async def test_get_verdict_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "risk_level": "high",
        "summary": "Test summary",
        "key_risks": ["risk1"],
        "immediate_actions": ["action1"],
        "confidence": 0.9,
        "finding_counts": {"total": 1, "high": 1},
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result["risk_level"] == "high"
    assert result["confidence"] == 0.9


@pytest.mark.asyncio
async def test_get_compliance_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "frameworks": {"owasp_llm": {"passed": True, "score": 1.0}},
        "overall_passed": True,
        "failed_controls": [],
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_compliance("scan-123")
    assert result["overall_passed"] is True


@pytest.mark.asyncio
async def test_get_policies_returns_list():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [
        {"policy_type": "cedar", "content": {"statement": "permit(...);"} },
        {"policy_type": "bedrock", "content": {"topicPolicyConfig": {}}},
    ]
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_policies("scan-123")
    assert len(result) == 2
    assert result[0]["policy_type"] == "cedar"


@pytest.mark.asyncio
async def test_get_policies_normalizes_dict_response():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "cedar": {"statement": "permit(...);"},
        "bedrock": {"topicPolicyConfig": {}},
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_policies("scan-123")
    assert len(result) == 2
    policy_types = {p["policy_type"] for p in result}
    assert policy_types == {"cedar", "bedrock"}
    assert result[0]["content"] is not None


@pytest.mark.asyncio
async def test_get_verdict_returns_empty_dict_on_404():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result == {}


# ---------------------------------------------------------------------------
# Integration test: confirmed_by stamped on auto-resolve
# ---------------------------------------------------------------------------

import datetime

from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id


async def _make_project(db_session) -> str:
    pid = generate_id("proj")
    repo = ProjectRepository(db_session)
    await repo.create(
        project_id=pid,
        name="Test Project",
        description="test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
    )
    await db_session.commit()
    return pid


@pytest.mark.asyncio
async def test_mass_ingest_stamps_confirmed_by_on_resolve(client, db_session):
    """Re-scan auto-resolve stamps confirmed_by on the finding."""
    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from sqlalchemy import select

    pid = await _make_project(db_session)
    find_repo = FindingRepository(db_session)

    # Create an existing open MASS finding
    ext_id = "mass-scan-old-find-001"
    await find_repo.create(
        finding_id=generate_id("find"),
        project_id=pid,
        environment="dev",
        category="security",
        severity="high",
        title="Old finding",
        source={"tool_name": "mass2", "system": "mass_scan", "external_id": ext_id},
        full_data={"finding_id": "find-001"},
        normalized=True,
        detected_at=datetime.datetime.now(datetime.timezone.utc),
        batch_id=None,
        status="open",
        schema_version="1.1",
    )
    await db_session.commit()

    # Ingest a new scan that does NOT include the old finding → should auto-resolve it
    payload = {
        "scan_id": "scan-new",
        "risk_score": 2.0,
        "categories_completed": ["jailbreak"],
        "findings": [],  # old finding absent → resolved
    }
    resp = await client.post(f"/api/v1/projects/{pid}/integrations/mass/ingest", json=payload)
    assert resp.status_code == 200
    assert resp.json()["findings_resolved"] == 1

    # Verify confirmed_by stamped
    stmt = select(FindingRow).where(
        FindingRow.project_id == pid,
        FindingRow.source["external_id"].as_string() == ext_id,
    )
    result = await db_session.execute(stmt)
    finding = result.scalar_one()
    assert finding.status == "resolved"
    assert finding.full_data.get("confirmed_by") == "mass2"
    assert finding.full_data.get("confirmed_scan_id") == "scan-new"


@pytest.mark.asyncio
async def test_enrich_from_mass_updates_marker_and_policies(db_session):
    """_enrich_from_mass updates the mass2_marker full_data and upserts scanner policies."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch
    from sqlalchemy import select

    from pearl.api.routes.scanning import _enrich_from_mass
    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository

    pid = await _make_project(db_session)

    # Create the mass2_marker finding
    find_repo = FindingRepository(db_session)
    marker_ext_id = f"mass-marker-{pid}"
    await find_repo.create(
        finding_id=generate_id("find"),
        project_id=pid,
        environment="dev",
        category="security",
        severity="info",
        title="MASS 2.0 Scan Marker",
        source={"tool_name": "mass2_marker", "system": "mass_scan", "external_id": marker_ext_id},
        full_data={"scan_id": "scan-001", "risk_score": 3.0},
        normalized=True,
        detected_at=datetime.datetime.now(datetime.timezone.utc),
        batch_id=None,
        status="open",
        schema_version="1.1",
    )
    await db_session.commit()

    # Mock MassClient methods
    mock_verdict = {"risk_level": "medium", "summary": "ok", "confidence": 0.8, "finding_counts": {}}
    mock_compliance = {"overall_passed": True, "frameworks": {}, "failed_controls": []}
    mock_policies = [{"policy_type": "cedar", "content": {"statement": "permit(...);"}}]

    # Create a session_factory that returns db_session as an async context manager
    @asynccontextmanager
    async def session_factory():
        yield db_session

    with patch("pearl.scanning.mass_bridge.MassClient.get_verdict", new=AsyncMock(return_value=mock_verdict)), \
         patch("pearl.scanning.mass_bridge.MassClient.get_compliance", new=AsyncMock(return_value=mock_compliance)), \
         patch("pearl.scanning.mass_bridge.MassClient.get_policies", new=AsyncMock(return_value=mock_policies)), \
         patch("pearl.api.routes.scanning.settings") as mock_settings:
        mock_settings.mass_url = "http://mass-test"
        mock_settings.mass_api_key = "test-key"
        await _enrich_from_mass(pid, "scan-001", session_factory)

    # Verify marker full_data updated
    stmt = select(FindingRow).where(
        FindingRow.project_id == pid,
        FindingRow.source["external_id"].as_string() == marker_ext_id,
    )
    result = await db_session.execute(stmt)
    marker = result.scalar_one()
    assert marker.full_data.get("verdict") == mock_verdict
    assert marker.full_data.get("compliance") == mock_compliance
    assert marker.full_data.get("has_agent_trace") is True

    # Verify scanner policy upserted
    policy_repo = ScannerPolicyRepository(db_session)
    policies = await policy_repo.list_by_project(pid, source="mass")
    assert len(policies) == 1
    assert policies[0].policy_type == "cedar"
