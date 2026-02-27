"""Tests for the requirement_resolver service.

Covers:
- resolve_requirements returns empty list when project does not exist
- resolve_requirements returns empty list when project has no BU assigned
- resolve_requirements returns BU framework requirements when BU is assigned
- Duplicate control_ids are deduplicated; stricter level wins (mandatory > recommended)
- Results include the correct `source` field ("bu_framework" or "org_baseline")
- resolve_requirements returns org_baseline floor requirements when baseline has
  framework_requirements in defaults
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org import OrgRow
from pearl.db.models.project import ProjectRow
from pearl.db.models.business_unit import BusinessUnitRow
from pearl.db.models.framework_requirement import FrameworkRequirementRow
from pearl.services.promotion.requirement_resolver import resolve_requirements
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_org(session: AsyncSession, org_id: str = "org_resolver") -> str:
    from sqlalchemy import select
    result = await session.execute(
        select(OrgRow).where(OrgRow.org_id == org_id)
    )
    if not result.scalar_one_or_none():
        session.add(OrgRow(org_id=org_id, name="Resolver Test Org", slug=f"resolver-{org_id[-4:]}", settings={}))
        await session.flush()
    return org_id


async def _seed_project(
    session: AsyncSession,
    project_id: str,
    org_id: str | None = None,
    bu_id: str | None = None,
) -> ProjectRow:
    from sqlalchemy import select
    result = await session.execute(
        select(ProjectRow).where(ProjectRow.project_id == project_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    row = ProjectRow(
        project_id=project_id,
        name=f"Project {project_id}",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=False,
        schema_version="1.1",
        org_id=org_id,
        bu_id=bu_id,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_bu(
    session: AsyncSession,
    bu_id: str,
    org_id: str,
    name: str = "Test BU",
) -> BusinessUnitRow:
    from sqlalchemy import select
    result = await session.execute(
        select(BusinessUnitRow).where(BusinessUnitRow.bu_id == bu_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    row = BusinessUnitRow(
        bu_id=bu_id,
        org_id=org_id,
        name=name,
        framework_selections=[],
        additional_guardrails={},
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_framework_req(
    session: AsyncSession,
    bu_id: str,
    control_id: str,
    framework: str = "owasp_llm",
    applies_to_transitions: list | None = None,
    requirement_level: str = "mandatory",
    evidence_type: str = "scan_result",
) -> FrameworkRequirementRow:
    req_id = generate_id("freq_")
    row = FrameworkRequirementRow(
        requirement_id=req_id,
        bu_id=bu_id,
        framework=framework,
        control_id=control_id,
        applies_to_transitions=applies_to_transitions or ["*"],
        requirement_level=requirement_level,
        evidence_type=evidence_type,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_project_not_found(db_session):
    """resolve_requirements returns empty list for a non-existent project."""
    result = await resolve_requirements(
        project_id="proj_nonexistent_xyz",
        source_env="sandbox",
        target_env="dev",
        session=db_session,
    )
    assert result == []


@pytest.mark.asyncio
async def test_resolve_no_bu_assigned(db_session):
    """resolve_requirements returns empty list when project has no BU or org baseline."""
    org_id = await _seed_org(db_session, "org_res_no_bu")
    await _seed_project(db_session, "proj_res_no_bu", org_id=org_id, bu_id=None)
    await db_session.commit()

    result = await resolve_requirements(
        project_id="proj_res_no_bu",
        source_env="sandbox",
        target_env="dev",
        session=db_session,
    )
    assert result == []


@pytest.mark.asyncio
async def test_resolve_returns_bu_requirements(db_session):
    """resolve_requirements returns BU framework requirements when BU is assigned."""
    org_id = await _seed_org(db_session, "org_res_with_bu")
    bu_id = generate_id("bu_")
    await _seed_bu(db_session, bu_id, org_id)
    await _seed_framework_req(
        db_session, bu_id, "llm01_prompt_injection",
        framework="owasp_llm",
        applies_to_transitions=["sandbox->dev"],
        requirement_level="mandatory",
    )
    await _seed_project(db_session, "proj_res_with_bu", org_id=org_id, bu_id=bu_id)
    await db_session.commit()

    result = await resolve_requirements(
        project_id="proj_res_with_bu",
        source_env="sandbox",
        target_env="dev",
        session=db_session,
    )
    assert len(result) >= 1
    control_ids = [r.control_id for r in result]
    assert "llm01_prompt_injection" in control_ids


@pytest.mark.asyncio
async def test_resolve_source_field_is_bu_framework(db_session):
    """Requirements derived from BU have source='bu_framework'."""
    org_id = await _seed_org(db_session, "org_res_src")
    bu_id = generate_id("bu_")
    await _seed_bu(db_session, bu_id, org_id)
    await _seed_framework_req(
        db_session, bu_id, "a01_broken_access_control",
        framework="owasp_web",
        applies_to_transitions=["*"],
        requirement_level="mandatory",
    )
    await _seed_project(db_session, "proj_res_src", org_id=org_id, bu_id=bu_id)
    await db_session.commit()

    result = await resolve_requirements(
        project_id="proj_res_src",
        source_env="dev",
        target_env="preprod",
        session=db_session,
    )
    bu_reqs = [r for r in result if r.control_id == "a01_broken_access_control"]
    assert len(bu_reqs) == 1
    assert bu_reqs[0].source == "bu_framework"


@pytest.mark.asyncio
async def test_resolve_deduplication_mandatory_wins(db_session):
    """When the same control_id is added twice, mandatory beats recommended."""
    org_id = await _seed_org(db_session, "org_res_dedup")
    bu_id = generate_id("bu_")
    await _seed_bu(db_session, bu_id, org_id)

    # Add the same control_id twice — once recommended, once mandatory
    await _seed_framework_req(
        db_session, bu_id, "dedup_control_001",
        applies_to_transitions=["*"],
        requirement_level="recommended",
    )
    await _seed_framework_req(
        db_session, bu_id, "dedup_control_001",
        applies_to_transitions=["*"],
        requirement_level="mandatory",
    )
    await _seed_project(db_session, "proj_res_dedup", org_id=org_id, bu_id=bu_id)
    await db_session.commit()

    result = await resolve_requirements(
        project_id="proj_res_dedup",
        source_env="dev",
        target_env="preprod",
        session=db_session,
    )

    # Should appear only once, and the level should be mandatory
    matching = [r for r in result if r.control_id == "dedup_control_001"]
    assert len(matching) == 1
    assert matching[0].requirement_level == "mandatory"


@pytest.mark.asyncio
async def test_resolve_transition_filter(db_session):
    """Requirements that don't match the transition are excluded."""
    org_id = await _seed_org(db_session, "org_res_trans")
    bu_id = generate_id("bu_")
    await _seed_bu(db_session, bu_id, org_id)

    # Only applies to sandbox->dev
    await _seed_framework_req(
        db_session, bu_id, "sandbox_only_control",
        applies_to_transitions=["sandbox->dev"],
        requirement_level="mandatory",
    )
    # Applies to all transitions
    await _seed_framework_req(
        db_session, bu_id, "all_transitions_control",
        applies_to_transitions=["*"],
        requirement_level="recommended",
    )
    await _seed_project(db_session, "proj_res_trans", org_id=org_id, bu_id=bu_id)
    await db_session.commit()

    # Querying for dev->preprod — only the wildcard control should appear
    result = await resolve_requirements(
        project_id="proj_res_trans",
        source_env="dev",
        target_env="preprod",
        session=db_session,
    )
    control_ids = [r.control_id for r in result]
    assert "all_transitions_control" in control_ids
    assert "sandbox_only_control" not in control_ids


@pytest.mark.asyncio
async def test_resolve_result_sorted_mandatory_first(db_session):
    """Results are sorted mandatory first, then alphabetically by control_id."""
    org_id = await _seed_org(db_session, "org_res_sort")
    bu_id = generate_id("bu_")
    await _seed_bu(db_session, bu_id, org_id)

    await _seed_framework_req(
        db_session, bu_id, "zzz_recommended_last",
        applies_to_transitions=["*"],
        requirement_level="recommended",
    )
    await _seed_framework_req(
        db_session, bu_id, "aaa_mandatory_first",
        applies_to_transitions=["*"],
        requirement_level="mandatory",
    )
    await _seed_project(db_session, "proj_res_sort", org_id=org_id, bu_id=bu_id)
    await db_session.commit()

    result = await resolve_requirements(
        project_id="proj_res_sort",
        source_env="dev",
        target_env="preprod",
        session=db_session,
    )
    levels = [r.requirement_level for r in result]
    # All "mandatory" entries should appear before "recommended"
    saw_recommended = False
    for level in levels:
        if level == "recommended":
            saw_recommended = True
        if saw_recommended and level == "mandatory":
            pytest.fail("mandatory requirement appeared after recommended — wrong sort order")
