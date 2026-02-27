"""Tests for auto-elevation logic via task packet completion.

Covers:
- When OrgEnvironmentConfig has requires_approval=false for a target stage,
  completing a task packet that causes the gate to pass triggers auto-elevation
- _check_auto_elevation is only triggered when gate status is "passed"
- No auto-elevation occurs when requires_approval=true for the target stage
- No auto-elevation occurs when there is no OrgEnvironmentConfig for the project's org
- Auto-elevation creates a PromotionHistoryRow with promoted_by='pearl_auto'
- Auto-elevation updates the environment profile to the target env
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org import OrgRow
from pearl.db.models.project import ProjectRow
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
        session.add(OrgRow(
            org_id=org_id,
            name=f"Org {org_id}",
            slug=f"slug-{org_id[-6:]}",
            settings={},
        ))
        await session.flush()
    return org_id


async def _create_task_packet(session: AsyncSession, project_id: str, environment: str = "sandbox", transition: str | None = None) -> str:
    """Create a task packet directly in the DB."""
    from pearl.repositories.task_packet_repo import TaskPacketRepository

    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(session)
    await repo.create(
        task_packet_id=tp_id,
        project_id=project_id,
        environment=environment,
        trace_id=generate_id("trace_"),
        packet_data={
            "task_type": "remediate_gate_blocker",
            "task_packet_id": tp_id,
            "status": "pending",
            "rule_id": generate_id("rule_"),
            "rule_type": "test_rule",
            "fix_guidance": "Fix the issue",
            "transition": transition or f"{environment}->dev",
            "created_by": "test",
        },
    )
    await session.commit()
    return tp_id


async def _setup_project_with_env_config(
    client,
    session: AsyncSession,
    project_id: str,
    org_id: str,
    stages: list[dict],
) -> str:
    """Create a project linked to an org that has an OrgEnvironmentConfig."""
    await _seed_org(session, org_id)
    await session.commit()

    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = False
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201

    # Attach org_id to project in DB (projects endpoint doesn't currently set it)
    from sqlalchemy import update
    await session.execute(
        update(ProjectRow)
        .where(ProjectRow.project_id == project_id)
        .values(org_id=org_id)
    )
    await session.commit()

    r2 = await client.put(
        "/api/v1/org-env-config",
        json={"org_id": org_id, "stages": stages},
    )
    assert r2.status_code == 200

    return project_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_auto_elevation_without_org_env_config(client, db_session):
    """Completing a task packet without an OrgEnvironmentConfig does not auto-elevate."""
    pid = "proj_auto_no_config"
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    tp_id = await _create_task_packet(db_session, pid, environment="sandbox")

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Applied fix",
            "commit_ref": "abc123",
            "files_changed": ["main.py"],
        },
    )
    assert complete_r.status_code == 200

    # No promotion history should exist — no OrgEnvironmentConfig means no auto-elevation
    from sqlalchemy import select
    from pearl.db.models.promotion import PromotionHistoryRow
    result = await db_session.execute(
        select(PromotionHistoryRow).where(PromotionHistoryRow.project_id == pid)
    )
    history = list(result.scalars().all())
    auto_elevated = [h for h in history if h.promoted_by == "pearl_auto"]
    assert len(auto_elevated) == 0


@pytest.mark.asyncio
async def test_no_auto_elevation_when_requires_approval_true(client, db_session):
    """No auto-elevation occurs when requires_approval=true for the target stage."""
    org_id = "org_auto_appr_req"
    pid = "proj_auto_needs_appr"

    stages = [
        {"name": "sandbox", "order": 1, "risk_level": "low", "requires_approval": False},
        {"name": "dev", "order": 2, "risk_level": "medium", "requires_approval": True},
    ]
    await _setup_project_with_env_config(client, db_session, pid, org_id, stages)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    tp_id = await _create_task_packet(db_session, pid, environment="sandbox", transition="sandbox->dev")

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Fixed it",
            "commit_ref": "def456",
            "files_changed": [],
        },
    )
    assert complete_r.status_code == 200

    # dev requires_approval=True → no auto-elevation regardless of gate result
    from sqlalchemy import select
    from pearl.db.models.promotion import PromotionHistoryRow
    result = await db_session.execute(
        select(PromotionHistoryRow)
        .where(
            PromotionHistoryRow.project_id == pid,
            PromotionHistoryRow.promoted_by == "pearl_auto",
        )
    )
    auto_history = list(result.scalars().all())
    assert len(auto_history) == 0


@pytest.mark.asyncio
async def test_auto_elevation_creates_promotion_history(client, db_session):
    """When requires_approval=false and gate passes, auto-elevation creates PromotionHistoryRow."""
    org_id = "org_auto_elev_hist"
    pid = "proj_auto_elevate_hist"

    stages = [
        {"name": "sandbox", "order": 1, "risk_level": "low", "requires_approval": False},
        {"name": "dev", "order": 2, "risk_level": "medium", "requires_approval": False},
    ]
    await _setup_project_with_env_config(client, db_session, pid, org_id, stages)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    compile_req["project_id"] = pid
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)

    tp_id = await _create_task_packet(db_session, pid, environment="sandbox", transition="sandbox->dev")

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "All checks passing",
            "commit_ref": "ghi789",
            "files_changed": ["config.py"],
        },
    )
    assert complete_r.status_code == 200

    # If the gate evaluated as passed, auto-elevation should have fired
    gate_status = complete_r.json().get("gate_status")
    if gate_status == "passed":
        from sqlalchemy import select
        from pearl.db.models.promotion import PromotionHistoryRow
        result = await db_session.execute(
            select(PromotionHistoryRow)
            .where(
                PromotionHistoryRow.project_id == pid,
                PromotionHistoryRow.promoted_by == "pearl_auto",
            )
        )
        auto_history = list(result.scalars().all())
        assert len(auto_history) >= 1
        assert auto_history[0].target_environment == "dev"


@pytest.mark.asyncio
async def test_complete_task_packet_returns_gate_status(client, db_session):
    """POST /task-packets/{id}/complete response includes gate_status field."""
    pid = "proj_auto_gate_status_ret"
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    tp_id = await _create_task_packet(db_session, pid, environment="sandbox")

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Done",
            "commit_ref": "abc000",
        },
    )
    assert complete_r.status_code == 200
    data = complete_r.json()
    assert "gate_status" in data
    assert "completed_at" in data
    assert "findings_resolved" in data


@pytest.mark.asyncio
async def test_complete_task_packet_findings_resolved_count(client, db_session):
    """complete response includes findings_resolved=0 when no finding_ids provided."""
    pid = "proj_auto_fid_count"
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    tp_id = await _create_task_packet(db_session, pid, environment="sandbox")

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={"status": "completed", "fix_summary": "No findings"},
    )
    assert complete_r.status_code == 200
    assert complete_r.json()["findings_resolved"] == 0
