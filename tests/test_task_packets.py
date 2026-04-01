"""Tests for task packet execution phase transitions.

Covers:
- Valid transition accepted (e.g. planning → coding, returns 200 with updated phase)
- Illegal backward transition rejected with 422 (e.g. coding → planning)
- Terminal state locked: complete → anything returns 422
- Terminal state locked: failed → anything returns 422
- phase_history accumulates correctly across multiple transitions (not replaced)
- failed reachable from a non-terminal phase (e.g. testing → failed)
- GET /task-packets/{id} response includes execution_phase and phase_history
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(client, project_id: str) -> str:
    """Create a minimal project for test isolation."""
    r = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": project_id,
            "name": f"Test Project {project_id}",
            "description": "Phase transition test project",
            "owner_team": "test-team",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": False,
        },
    )
    assert r.status_code == 201, f"Failed to create project: {r.text}"
    return project_id


async def _create_task_packet(
    db_session: AsyncSession,
    project_id: str,
    environment: str = "sandbox",
) -> str:
    """Create a task packet directly in the DB (bypasses compiled package requirement)."""
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


async def _patch_phase(client, tp_id: str, phase: str, agent_id: str = "test-agent") -> dict:
    """Helper to PATCH phase on a task packet and return the response."""
    r = await client.patch(
        f"/api/v1/task-packets/{tp_id}/phase",
        json={"phase": phase, "agent_id": agent_id},
    )
    return r


# ---------------------------------------------------------------------------
# Tests — valid transitions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_transition_planning_to_coding(client, db_session):
    """planning → coding is a valid transition; returns 200 with updated phase."""
    pid = await _create_project(client, "proj_phase_p2c")
    tp_id = await _create_task_packet(db_session, pid)

    r = await _patch_phase(client, tp_id, "coding")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["execution_phase"] == "coding"
    assert data["task_packet_id"] == tp_id


@pytest.mark.asyncio
async def test_valid_transition_coding_to_testing(client, db_session):
    """coding → testing is a valid transition."""
    pid = await _create_project(client, "proj_phase_c2t")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    r = await _patch_phase(client, tp_id, "testing")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "testing"


@pytest.mark.asyncio
async def test_valid_transition_testing_to_review(client, db_session):
    """testing → review is a valid transition."""
    pid = await _create_project(client, "proj_phase_t2r")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    r = await _patch_phase(client, tp_id, "review")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "review"


@pytest.mark.asyncio
async def test_valid_transition_review_to_complete(client, db_session):
    """review → complete is a valid transition."""
    pid = await _create_project(client, "proj_phase_r2c")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    await _patch_phase(client, tp_id, "review")
    r = await _patch_phase(client, tp_id, "complete")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "complete"


# ---------------------------------------------------------------------------
# Tests — illegal transitions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_illegal_backward_transition_coding_to_planning(client, db_session):
    """coding → planning is illegal and returns 422."""
    pid = await _create_project(client, "proj_phase_back_c2p")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    r = await _patch_phase(client, tp_id, "planning")
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_illegal_skip_transition_planning_to_testing(client, db_session):
    """planning → testing skips coding and is illegal; returns 422."""
    pid = await _create_project(client, "proj_phase_skip_p2t")
    tp_id = await _create_task_packet(db_session, pid)

    r = await _patch_phase(client, tp_id, "testing")
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_illegal_transition_review_to_coding(client, db_session):
    """review → coding is an illegal backward transition; returns 422."""
    pid = await _create_project(client, "proj_phase_back_r2c")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    await _patch_phase(client, tp_id, "review")
    r = await _patch_phase(client, tp_id, "coding")
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Tests — terminal state locking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminal_complete_blocks_further_transitions(client, db_session):
    """Once in 'complete', any further transition returns 422."""
    pid = await _create_project(client, "proj_phase_term_complete")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    await _patch_phase(client, tp_id, "review")
    await _patch_phase(client, tp_id, "complete")

    for target in ["planning", "coding", "testing", "review", "failed"]:
        r = await _patch_phase(client, tp_id, target)
        assert r.status_code == 422, f"Expected 422 when transitioning from 'complete' to '{target}', got {r.status_code}"


@pytest.mark.asyncio
async def test_terminal_failed_blocks_further_transitions(client, db_session):
    """Once in 'failed', any further transition returns 422."""
    pid = await _create_project(client, "proj_phase_term_failed")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "failed")

    for target in ["planning", "coding", "testing", "review", "complete"]:
        r = await _patch_phase(client, tp_id, target)
        assert r.status_code == 422, f"Expected 422 when transitioning from 'failed' to '{target}', got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests — failed reachable from non-terminal phases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_reachable_from_planning(client, db_session):
    """planning → failed is valid."""
    pid = await _create_project(client, "proj_phase_plan_fail")
    tp_id = await _create_task_packet(db_session, pid)

    r = await _patch_phase(client, tp_id, "failed")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "failed"


@pytest.mark.asyncio
async def test_failed_reachable_from_testing(client, db_session):
    """testing → failed is a valid transition."""
    pid = await _create_project(client, "proj_phase_test_fail")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    r = await _patch_phase(client, tp_id, "failed")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "failed"


@pytest.mark.asyncio
async def test_failed_reachable_from_review(client, db_session):
    """review → failed is a valid transition."""
    pid = await _create_project(client, "proj_phase_review_fail")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")
    await _patch_phase(client, tp_id, "testing")
    await _patch_phase(client, tp_id, "review")
    r = await _patch_phase(client, tp_id, "failed")
    assert r.status_code == 200
    assert r.json()["execution_phase"] == "failed"


# ---------------------------------------------------------------------------
# Tests — phase_history accumulation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase_history_accumulates_across_transitions(client, db_session):
    """phase_history grows with each transition and is not replaced."""
    pid = await _create_project(client, "proj_phase_history_accum")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding", agent_id="agent-a")
    await _patch_phase(client, tp_id, "testing", agent_id="agent-b")
    r = await _patch_phase(client, tp_id, "review", agent_id="agent-c")

    assert r.status_code == 200
    history = r.json()["phase_history"]
    # Should have exactly 3 entries (one per transition)
    assert len(history) == 3, f"Expected 3 history entries, got {len(history)}: {history}"
    assert history[0]["phase"] == "coding"
    assert history[1]["phase"] == "testing"
    assert history[2]["phase"] == "review"


@pytest.mark.asyncio
async def test_phase_history_entry_has_required_fields(client, db_session):
    """Each phase_history entry includes 'phase', 'timestamp', and 'agent_id'."""
    pid = await _create_project(client, "proj_phase_history_fields")
    tp_id = await _create_task_packet(db_session, pid)

    r = await _patch_phase(client, tp_id, "coding", agent_id="test-agent-001")
    assert r.status_code == 200
    history = r.json()["phase_history"]
    assert len(history) == 1
    entry = history[0]
    assert entry["phase"] == "coding"
    assert "timestamp" in entry
    assert entry["agent_id"] == "test-agent-001"


@pytest.mark.asyncio
async def test_phase_history_full_progression(client, db_session):
    """Full planning → coding → testing → review → complete builds correct 4-entry history."""
    pid = await _create_project(client, "proj_phase_history_full")
    tp_id = await _create_task_packet(db_session, pid)

    phases = ["coding", "testing", "review", "complete"]
    for phase in phases:
        await _patch_phase(client, tp_id, phase)

    # Verify via GET
    r = await client.get(f"/api/v1/task-packets/{tp_id}")
    assert r.status_code == 200
    data = r.json()
    history = data["phase_history"]
    assert len(history) == 4
    assert [h["phase"] for h in history] == phases


# ---------------------------------------------------------------------------
# Tests — GET includes execution_phase and phase_history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_task_packet_includes_execution_phase(client, db_session):
    """GET /task-packets/{id} includes 'execution_phase' with default 'planning'."""
    pid = await _create_project(client, "proj_phase_get_default")
    tp_id = await _create_task_packet(db_session, pid)

    r = await client.get(f"/api/v1/task-packets/{tp_id}")
    assert r.status_code == 200
    data = r.json()
    assert "execution_phase" in data
    assert data["execution_phase"] == "planning"


@pytest.mark.asyncio
async def test_get_task_packet_includes_phase_history(client, db_session):
    """GET /task-packets/{id} includes 'phase_history' (empty list by default)."""
    pid = await _create_project(client, "proj_phase_get_history")
    tp_id = await _create_task_packet(db_session, pid)

    r = await client.get(f"/api/v1/task-packets/{tp_id}")
    assert r.status_code == 200
    data = r.json()
    assert "phase_history" in data
    assert data["phase_history"] == []


@pytest.mark.asyncio
async def test_get_task_packet_reflects_current_phase_after_transition(client, db_session):
    """GET /task-packets/{id} returns the current phase after a transition."""
    pid = await _create_project(client, "proj_phase_get_updated")
    tp_id = await _create_task_packet(db_session, pid)

    await _patch_phase(client, tp_id, "coding")

    r = await client.get(f"/api/v1/task-packets/{tp_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["execution_phase"] == "coding"
    assert len(data["phase_history"]) == 1
    assert data["phase_history"][0]["phase"] == "coding"


# ---------------------------------------------------------------------------
# Tests — invalid phase name
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_phase_name_returns_422(client, db_session):
    """Requesting an unknown phase name returns 422."""
    pid = await _create_project(client, "proj_phase_invalid_name")
    tp_id = await _create_task_packet(db_session, pid)

    r = await _patch_phase(client, tp_id, "deploying")  # not a valid phase
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Tests — 404 for missing packet
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_phase_not_found(client):
    """PATCH /task-packets/{id}/phase returns 404 for nonexistent packet."""
    r = await client.patch(
        "/api/v1/task-packets/tp_nonexistent_phase_xyz/phase",
        json={"phase": "coding"},
    )
    assert r.status_code == 404
