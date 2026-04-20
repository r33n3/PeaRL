"""Integration tests for the factory run summary route and deregister-triggered materialization.

Tests use the shared ``client`` and ``db_session`` fixtures from conftest.py.
The app runs against an in-memory SQLite DB — no external services required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pearl.db.models.governance_telemetry import ClientCostEntryRow
from pearl.db.models.project import ProjectRow
from pearl.db.models.task_packet import TaskPacketRow
from pearl.db.models.workload import WorkloadRow
from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_project(db_session, project_id: str) -> ProjectRow:
    row = ProjectRow(
        project_id=project_id,
        name="Route Integration Test Project",
        description="auto-seeded",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal_only",
        ai_enabled=True,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_task_packet(db_session, project_id: str, tp_id: str) -> TaskPacketRow:
    row = TaskPacketRow(
        task_packet_id=tp_id,
        project_id=project_id,
        environment="sandbox",
        packet_data={},
        trace_id=generate_id("trc"),
        execution_phase="planning",
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_workload(
    db_session,
    svid: str,
    task_packet_id: str,
    workload_id: str | None = None,
) -> WorkloadRow:
    now = datetime.now(timezone.utc)
    row = WorkloadRow(
        workload_id=workload_id or generate_id("wkld_"),
        svid=svid,
        task_packet_id=task_packet_id,
        registered_at=now,
        last_seen_at=now,
        status="active",
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_cost_entry(
    db_session,
    project_id: str,
    frun_id: str,
    *,
    cost_usd: float = 0.05,
    model: str = "claude-3-sonnet",
) -> None:
    entry = ClientCostEntryRow(
        entry_id=generate_id("ce"),
        project_id=project_id,
        timestamp=datetime.now(timezone.utc),
        environment="sandbox",
        workflow="test_workflow",
        model=model,
        cost_usd=cost_usd,
        duration_ms=1000,
        tools_called=[],
        session_id=frun_id,
    )
    db_session.add(entry)
    await db_session.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_summary_returns_404_when_missing(client):
    """GET run-summaries/{frun_id} returns 404 when no summary exists."""
    response = await client.get("/api/v1/workloads/run-summaries/nonexistent_frun")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_summary_returns_200_when_present(client, db_session):
    """GET run-summaries/{frun_id} returns 200 with expected fields when summary exists."""
    project_id = generate_id("proj_")
    frun_id = generate_id("frun_")

    await _seed_project(db_session, project_id)

    repo = FactoryRunSummaryRepository(db_session)
    await repo.upsert(
        {
            "frun_id": frun_id,
            "project_id": project_id,
            "task_packet_id": None,
            "goal_id": "goal-abc",
            "svid": "spiffe://example.org/agent1",
            "environment": "sandbox",
            "outcome": "achieved",
            "total_cost_usd": 0.42,
            "models_used": ["claude-3-sonnet"],
            "tools_called": ["bash", "read"],
            "duration_ms": 5000,
            "anomaly_flags": [],
            "promoted": False,
            "promotion_env": None,
            "started_at": None,
            "completed_at": None,
        }
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/workloads/run-summaries/{frun_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["frun_id"] == frun_id
    assert data["outcome"] == "achieved"
    assert data["total_cost_usd"] == pytest.approx(0.42, rel=1e-3)
    assert data["models_used"] == ["claude-3-sonnet"]


@pytest.mark.asyncio
async def test_delete_workload_with_frun_id_triggers_materialization(client, db_session):
    """DELETE /workloads/{svid}?frun_id={frun_id} materializes the run summary."""
    project_id = generate_id("proj_")
    tp_id = generate_id("tp_")
    svid = f"spiffe://test.example/{generate_id('agent')}"
    frun_id = generate_id("frun_")

    # Seed project, task packet, workload, and a cost entry
    await _seed_project(db_session, project_id)
    await _seed_task_packet(db_session, project_id, tp_id)
    await _seed_workload(db_session, svid, tp_id)
    await _seed_cost_entry(db_session, project_id, frun_id, cost_usd=0.10)
    await db_session.commit()

    # Deregister the workload and trigger materialization
    response = await client.delete(
        f"/api/v1/workloads/{svid}",
        params={"frun_id": frun_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"

    # Run summary should now exist
    summary_response = await client.get(f"/api/v1/workloads/run-summaries/{frun_id}")
    assert summary_response.status_code == 200
    data = summary_response.json()
    assert data["frun_id"] == frun_id
    assert data["total_cost_usd"] == pytest.approx(0.10, rel=1e-3)
