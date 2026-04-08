"""Tests for scanner policy entries in recommended-guardrails response."""
import pytest
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
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
async def test_recommended_guardrails_includes_scanner_policies(client, db_session):
    """Scanner policies from scanner_policy_store appear in recommended-guardrails response."""
    pid = await _make_project(db_session)

    # Seed a MASS policy
    policy_repo = ScannerPolicyRepository(db_session)
    await policy_repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan-001",
        policy_type="cedar",
        content={"statement": "permit(principal, action, resource);"},
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{pid}/recommended-guardrails")
    assert resp.status_code == 200
    data = resp.json()

    scanner_entries = [g for g in data["recommended_guardrails"] if g.get("source") == "mass"]
    assert len(scanner_entries) == 1
    entry = scanner_entries[0]
    assert entry["policy_type"] == "cedar"
    assert entry["source"] == "mass"
    assert "content" in entry


@pytest.mark.asyncio
async def test_pearl_generated_guardrails_have_pearl_source(client, db_session):
    """PeaRL-generated guardrails have source='pearl'."""
    pid = await _make_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/recommended-guardrails")
    assert resp.status_code == 200
    data = resp.json()

    for g in data["recommended_guardrails"]:
        assert "source" in g, f"guardrail {g.get('id')} missing source field"
