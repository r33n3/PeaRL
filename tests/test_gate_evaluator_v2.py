"""Tests for gate evaluator with BU-derived requirements.

Covers:
- Gate evaluation injects FRAMEWORK_CONTROL_REQUIRED rules from BU requirements
- FAIL result for a gate rule triggers idempotent TaskPacket creation
- Second evaluation with the same failing rule does not create duplicate TaskPackets
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org import OrgRow
from pearl.db.models.business_unit import BusinessUnitRow
from pearl.db.models.framework_requirement import FrameworkRequirementRow
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.id_generator import generate_id

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_org(session: AsyncSession, org_id: str) -> str:
    from sqlalchemy import select
    result = await session.execute(select(OrgRow).where(OrgRow.org_id == org_id))
    if not result.scalar_one_or_none():
        session.add(OrgRow(org_id=org_id, name=f"Org {org_id}", slug=f"slug-{org_id[-6:]}", settings={}))
        await session.flush()
    return org_id


async def _seed_bu_with_requirements(
    session: AsyncSession,
    bu_id: str,
    org_id: str,
    controls: list[dict],
) -> BusinessUnitRow:
    """Create a BU and seed FrameworkRequirementRows for it."""
    from sqlalchemy import select
    result = await session.execute(select(BusinessUnitRow).where(BusinessUnitRow.bu_id == bu_id))
    bu = result.scalar_one_or_none()
    if not bu:
        bu = BusinessUnitRow(
            bu_id=bu_id,
            org_id=org_id,
            name=f"BU {bu_id}",
            framework_selections=[],
            additional_guardrails={},
        )
        session.add(bu)
        await session.flush()

    for ctrl in controls:
        session.add(FrameworkRequirementRow(
            requirement_id=generate_id("freq_"),
            bu_id=bu_id,
            framework=ctrl.get("framework", "owasp_llm"),
            control_id=ctrl["control_id"],
            applies_to_transitions=ctrl.get("applies_to_transitions", ["*"]),
            requirement_level=ctrl.get("requirement_level", "mandatory"),
            evidence_type=ctrl.get("evidence_type", "scan_result"),
        ))
    await session.flush()
    return bu


async def _setup_full_project(client, project_id: str, ai_enabled: bool = False):
    """Create a minimally provisioned project suitable for gate evaluation."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = ai_enabled
    await client.post("/api/v1/projects", json=project)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{project_id}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{project_id}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{project_id}/environment-profile", json=profile)

    return project_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_includes_framework_control_required_rules(client, db_session):
    """Gate evaluation injects FRAMEWORK_CONTROL_REQUIRED rules from BU requirements."""
    org_id = await _seed_org(db_session, "org_gate_v2_inject")
    bu_id = generate_id("bu_")
    await _seed_bu_with_requirements(
        db_session,
        bu_id,
        org_id,
        controls=[
            {
                "control_id": "llm01_prompt_injection",
                "framework": "owasp_llm",
                "applies_to_transitions": ["*"],
                "requirement_level": "mandatory",
                "evidence_type": "scan_result",
            }
        ],
    )
    await db_session.commit()

    pid = "proj_gate_v2_inject"
    await _setup_full_project(client, pid)

    # Assign the BU to the project directly in DB
    from sqlalchemy import update
    from pearl.db.models.project import ProjectRow
    await db_session.execute(
        update(ProjectRow)
        .where(ProjectRow.project_id == pid)
        .values(bu_id=bu_id, org_id=org_id)
    )
    await db_session.commit()

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()

    rule_types = [rr["rule_type"] for rr in data.get("rule_results", [])]
    assert "framework_control_required" in rule_types


@pytest.mark.asyncio
async def test_failed_rule_creates_task_packet(client, db_session):
    """A FAIL result for any gate rule creates a TaskPacket for the project."""
    pid = "proj_gate_v2_tp_create"
    # No baseline → org_baseline_attached rule will FAIL and create a TaskPacket
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()

    failed = [rr for rr in data.get("rule_results", []) if rr["result"] == "fail"]
    assert len(failed) >= 1, "Expected at least one failed rule to trigger TaskPacket creation"

    # TaskPackets should have been created for failed rules
    tp_repo = TaskPacketRepository(db_session)
    packets = await tp_repo.list_by_project(pid)
    assert len(packets) >= 1

    packet_rule_types = {(p.packet_data or {}).get("task_type") for p in packets}
    assert "remediate_gate_blocker" in packet_rule_types


@pytest.mark.asyncio
async def test_second_evaluation_no_duplicate_task_packets(client, db_session):
    """Evaluating twice with the same failing rule does not duplicate TaskPackets."""
    pid = "proj_gate_v2_no_dup"
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    # First evaluation
    r1 = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r1.status_code == 200

    tp_repo = TaskPacketRepository(db_session)
    packets_after_first = await tp_repo.list_by_project(pid)
    count_after_first = len(packets_after_first)
    assert count_after_first >= 1

    # Second evaluation — same gate failure
    r2 = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r2.status_code == 200

    # Need a fresh session query to see the state after second evaluation
    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.project_id == pid)
    )
    packets_after_second = list(result.scalars().all())

    # The second evaluation should NOT have added new task packets for the same rules
    # Open task packets (not completed) should be the same count
    open_after_first = [
        p for p in packets_after_first
        if (p.packet_data or {}).get("status") in ("pending", "in_progress")
        and p.completed_at is None
    ]
    open_after_second = [
        p for p in packets_after_second
        if (p.packet_data or {}).get("status") in ("pending", "in_progress")
        and p.completed_at is None
    ]
    assert len(open_after_second) == len(open_after_first), (
        f"Duplicate TaskPackets created: {len(open_after_second)} after second eval "
        f"vs {len(open_after_first)} after first"
    )


@pytest.mark.asyncio
async def test_gate_evaluation_rule_results_structure(client, db_session):
    """Gate evaluation rule_results contain required fields."""
    pid = "proj_gate_v2_struct"
    await _setup_full_project(client, pid)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()

    assert "rule_results" in data
    assert len(data["rule_results"]) > 0

    for rr in data["rule_results"]:
        assert "rule_type" in rr
        assert "result" in rr
        assert rr["result"] in ("pass", "fail", "skip", "exception")
        assert "rule_id" in rr


@pytest.mark.asyncio
async def test_bu_framework_requirements_visible_in_evaluation(client, db_session):
    """BU framework requirements appear in the gate evaluation rule results."""
    org_id = await _seed_org(db_session, "org_gate_v2_visible")
    bu_id = generate_id("bu_")
    # Use a real owasp_llm control that has a known handler
    unique_control = "llm02_insecure_output_handling"
    await _seed_bu_with_requirements(
        db_session,
        bu_id,
        org_id,
        controls=[
            {
                "control_id": unique_control,
                "framework": "owasp_llm",
                "applies_to_transitions": ["*"],
                "requirement_level": "mandatory",
                "evidence_type": "scan_result",
            }
        ],
    )
    await db_session.commit()

    pid = "proj_gate_v2_visible"
    await _setup_full_project(client, pid)

    from sqlalchemy import update
    from pearl.db.models.project import ProjectRow
    await db_session.execute(
        update(ProjectRow)
        .where(ProjectRow.project_id == pid)
        .values(bu_id=bu_id, org_id=org_id)
    )
    await db_session.commit()

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()

    # framework_control_required rule type should appear in rule_results
    framework_rules = [
        rr for rr in data.get("rule_results", [])
        if rr.get("rule_type") == "framework_control_required"
    ]
    assert len(framework_rules) >= 1, "Expected at least one framework_control_required rule from BU requirements"

    # At least one should reference the owasp_llm framework in its details
    owasp_rules = [
        rr for rr in framework_rules
        if (rr.get("details") or {}).get("framework") == "owasp_llm"
    ]
    assert len(owasp_rules) >= 1, "Expected at least one owasp_llm framework rule from BU"
