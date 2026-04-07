"""Tests for ScannerPolicyRepository — upsert and list operations."""

import pytest

from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
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
async def test_upsert_creates_new_row(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)

    row = await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan_001",
        policy_type="cedar",
        content={"policy": "permit(principal, action, resource);"},
    )
    await db_session.commit()

    rows = await repo.list_by_project(pid)
    assert len(rows) == 1
    assert rows[0].id == row.id
    assert rows[0].source == "mass"
    assert rows[0].scan_id == "scan_001"
    assert rows[0].policy_type == "cedar"
    assert rows[0].content == {"policy": "permit(principal, action, resource);"}


@pytest.mark.asyncio
async def test_upsert_replaces_existing_row(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)

    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan_001",
        policy_type="cedar",
        content={"policy": "old content"},
    )
    await db_session.commit()

    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan_002",
        policy_type="cedar",
        content={"policy": "new content"},
    )
    await db_session.commit()

    rows = await repo.list_by_project(pid)
    assert len(rows) == 1
    assert rows[0].scan_id == "scan_002"
    assert rows[0].content == {"policy": "new content"}


@pytest.mark.asyncio
async def test_list_by_project_filters_by_source(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)

    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan_mass_001",
        policy_type="cedar",
        content={"policy": "mass policy"},
    )
    await repo.upsert(
        project_id=pid,
        source="snyk",
        scan_id="scan_snyk_001",
        policy_type="bedrock",
        content={"policy": "snyk policy"},
    )
    await db_session.commit()

    mass_rows = await repo.list_by_project(pid, source="mass")
    assert len(mass_rows) == 1
    assert mass_rows[0].source == "mass"
    assert mass_rows[0].scan_id == "scan_mass_001"
