"""Tests for the task packet remediation loop.

Covers:
- POST /task-packets/{id}/complete stores outcome data (fix_summary, commit_ref, files_changed)
- After completion, DB reflects updated status and outcome
- If finding_ids_resolved provided, those findings are updated to status="resolved"
- Completing an already-completed task packet overwrites outcome (no conflict)
- Claim before complete: agent_id and claimed_at are set
- Attempting to claim an already-claimed (in-progress) task packet returns 409
- Complete returns findings_resolved count matching the number of resolved finding IDs
- Complete without finding_ids_resolved resolves no findings (count=0)
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(client, project_id: str) -> str:
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = False
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201
    return project_id


async def _create_task_packet(db_session: AsyncSession, project_id: str, environment: str = "sandbox") -> str:
    """Create a task packet directly in the DB (bypasses compiled package requirement)."""
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    from pearl.services.id_generator import generate_id

    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(db_session)
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
            "transition": f"{environment}->dev",
            "created_by": "test",
        },
    )
    await db_session.commit()
    return tp_id


async def _ingest_finding(client, project_id: str, finding_id: str, severity: str = "high") -> str:
    from pearl.services.id_generator import generate_id
    findings_req = load_example("findings/findings-ingest.request.json")
    # Use unique batch_id per call to avoid UNIQUE constraint violations
    findings_req["source_batch"]["batch_id"] = generate_id("batch_")
    findings_req["findings"][0]["project_id"] = project_id
    findings_req["findings"][0]["finding_id"] = finding_id
    findings_req["findings"][0]["severity"] = severity
    r = await client.post("/api/v1/findings/ingest", json=findings_req)
    assert r.status_code in (200, 201, 202)
    return finding_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_stores_fix_summary(client, db_session):
    """POST /task-packets/{id}/complete stores fix_summary in outcome."""
    pid = await _create_project(client, "proj_tp_fix_summary")
    tp_id = await _create_task_packet(db_session, pid)

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Applied security patch to input validation",
            "commit_ref": "abc123def",
            "files_changed": ["src/validator.py", "tests/test_validator.py"],
        },
    )
    assert complete_r.status_code == 200
    data = complete_r.json()
    assert data["packet_id"] == tp_id
    assert data["status"] == "completed"
    assert "completed_at" in data

    # Verify outcome stored in DB
    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.task_packet_id == tp_id)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.completed_at is not None
    assert row.outcome is not None
    assert row.outcome["fix_summary"] == "Applied security patch to input validation"
    assert row.outcome["commit_ref"] == "abc123def"
    assert "src/validator.py" in row.outcome["files_changed"]


@pytest.mark.asyncio
async def test_complete_stores_commit_ref_and_files_changed(client, db_session):
    """Outcome includes commit_ref and files_changed as submitted."""
    pid = await _create_project(client, "proj_tp_commit_ref")
    tp_id = await _create_task_packet(db_session, pid)

    files = ["app/routes.py", "app/models.py", "config/settings.py"]
    commit = "deadbeef1234567890"

    await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Patched three files",
            "commit_ref": commit,
            "files_changed": files,
        },
    )

    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.task_packet_id == tp_id)
    )
    row = result.scalar_one_or_none()
    assert row.outcome["commit_ref"] == commit
    assert sorted(row.outcome["files_changed"]) == sorted(files)


@pytest.mark.asyncio
async def test_complete_reflects_in_packet_data_status(client, db_session):
    """After completion, packet_data['status'] is updated to the submitted status."""
    pid = await _create_project(client, "proj_tp_data_status")
    tp_id = await _create_task_packet(db_session, pid)

    await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={"status": "completed", "fix_summary": "Done"},
    )

    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.task_packet_id == tp_id)
    )
    row = result.scalar_one_or_none()
    assert (row.packet_data or {}).get("status") == "completed"


@pytest.mark.asyncio
async def test_complete_resolves_findings(client, db_session):
    """finding_ids_resolved in complete request marks those findings as 'resolved'."""
    pid = await _create_project(client, "proj_tp_resolve_findings")
    finding_id = await _ingest_finding(client, pid, "find_tp_resolve_001", severity="high")
    tp_id = await _create_task_packet(db_session, pid)

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Fixed the finding",
            "finding_ids_resolved": [finding_id],
        },
    )
    assert complete_r.status_code == 200
    data = complete_r.json()
    assert data["findings_resolved"] == 1

    # Verify finding status is now "resolved"
    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    result = await db_session.execute(
        select(FindingRow).where(FindingRow.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    assert finding is not None
    assert finding.status == "resolved"


@pytest.mark.asyncio
async def test_complete_no_finding_ids_resolves_zero(client, db_session):
    """Completing without finding_ids_resolved resolves no findings."""
    pid = await _create_project(client, "proj_tp_no_findings")
    await _ingest_finding(client, pid, "find_tp_untouched_001")
    tp_id = await _create_task_packet(db_session, pid)

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={"status": "completed", "fix_summary": "Nothing resolved"},
    )
    assert complete_r.status_code == 200
    assert complete_r.json()["findings_resolved"] == 0

    # Original finding should still be open
    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    result = await db_session.execute(
        select(FindingRow).where(FindingRow.finding_id == "find_tp_untouched_001")
    )
    finding = result.scalar_one_or_none()
    assert finding is not None
    assert finding.status != "resolved"


@pytest.mark.asyncio
async def test_complete_multiple_findings_resolved(client, db_session):
    """Multiple findings can be resolved in a single complete request."""
    pid = await _create_project(client, "proj_tp_multi_resolve")
    fid1 = await _ingest_finding(client, pid, "find_tp_multi_001")
    fid2 = await _ingest_finding(client, pid, "find_tp_multi_002")
    fid3 = await _ingest_finding(client, pid, "find_tp_multi_003")
    tp_id = await _create_task_packet(db_session, pid)

    complete_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Fixed all three",
            "finding_ids_resolved": [fid1, fid2, fid3],
        },
    )
    assert complete_r.status_code == 200
    assert complete_r.json()["findings_resolved"] == 3

    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    for fid in [fid1, fid2, fid3]:
        result = await db_session.execute(
            select(FindingRow).where(FindingRow.finding_id == fid)
        )
        f = result.scalar_one_or_none()
        assert f is not None
        assert f.status == "resolved", f"Finding {fid} should be resolved"


@pytest.mark.asyncio
async def test_complete_not_found(client):
    """POST /task-packets/{id}/complete returns 404 for a non-existent packet."""
    r = await client.post(
        "/api/v1/task-packets/tp_nonexistent_xyz/complete",
        json={"status": "completed", "fix_summary": "Ghost fix"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_claim_sets_agent_id_and_status(client, db_session):
    """POST /task-packets/{id}/claim sets agent_id and in_progress status."""
    pid = await _create_project(client, "proj_tp_claim")
    tp_id = await _create_task_packet(db_session, pid)

    claim_r = await client.post(
        f"/api/v1/task-packets/{tp_id}/claim",
        json={"agent_id": "agent_claimer_007"},
    )
    assert claim_r.status_code == 200
    data = claim_r.json()
    assert data["agent_id"] == "agent_claimer_007"
    assert data["status"] == "in_progress"

    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.task_packet_id == tp_id)
    )
    row = result.scalar_one_or_none()
    assert row.agent_id == "agent_claimer_007"
    assert row.claimed_at is not None
    assert (row.packet_data or {}).get("status") == "in_progress"


@pytest.mark.asyncio
async def test_claim_conflict_when_already_claimed(client, db_session):
    """POST /task-packets/{id}/claim returns 409 if the packet is already claimed."""
    pid = await _create_project(client, "proj_tp_claim_conflict")
    tp_id = await _create_task_packet(db_session, pid)

    # First claim
    r1 = await client.post(
        f"/api/v1/task-packets/{tp_id}/claim",
        json={"agent_id": "agent_first"},
    )
    assert r1.status_code == 200

    # Second claim on the same uncompleted packet → conflict
    r2 = await client.post(
        f"/api/v1/task-packets/{tp_id}/claim",
        json={"agent_id": "agent_second"},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_complete_outcome_stored_in_db(client, db_session):
    """Outcome dict stored in DB matches what was submitted in the complete request."""
    pid = await _create_project(client, "proj_tp_outcome_db")
    tp_id = await _create_task_packet(db_session, pid)

    await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "partial",
            "fix_summary": "Partial fix applied",
            "commit_ref": "partial_commit_ref",
            "files_changed": ["partial_file.py"],
            "evidence_notes": "Only 70% complete, needs follow-up",
        },
    )

    from sqlalchemy import select
    from pearl.db.models.task_packet import TaskPacketRow
    result = await db_session.execute(
        select(TaskPacketRow).where(TaskPacketRow.task_packet_id == tp_id)
    )
    row = result.scalar_one_or_none()
    assert row.outcome is not None
    assert row.outcome["status"] == "partial"
    assert row.outcome["fix_summary"] == "Partial fix applied"
    assert row.outcome["commit_ref"] == "partial_commit_ref"
    assert row.outcome["evidence_notes"] == "Only 70% complete, needs follow-up"
    assert row.completed_at is not None
