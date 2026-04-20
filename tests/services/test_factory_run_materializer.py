"""Unit tests for factory_run materializer service.

All tests run against an in-memory SQLite DB via the shared db_session fixture.
No HTTP client needed — we call the service function directly.
"""

import os
import pytest
from datetime import datetime, timezone

os.environ.setdefault("PEARL_LOCAL", "1")

from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(db_session, project_id: str | None = None) -> str:
    """Insert a minimal project row. Returns project_id."""
    from pearl.repositories.project_repo import ProjectRepository

    pid = project_id or generate_id("proj")
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


async def _create_cost_entry(
    db_session,
    frun_id: str,
    project_id: str,
    *,
    cost_usd: float = 0.05,
    model: str = "claude-3-sonnet",
    tools_called: list[str] | None = None,
    duration_ms: int | None = 1000,
    environment: str = "sandbox",
) -> None:
    """Insert a ClientCostEntryRow for the given frun_id (session_id)."""
    from pearl.db.models.governance_telemetry import ClientCostEntryRow

    entry = ClientCostEntryRow(
        entry_id=generate_id("ce"),
        project_id=project_id,
        timestamp=datetime.now(timezone.utc),
        environment=environment,
        workflow="test_workflow",
        model=model,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        tools_called=tools_called or [],
        session_id=frun_id,
    )
    db_session.add(entry)
    await db_session.commit()


async def _create_task_packet(
    db_session,
    project_id: str,
    *,
    outcome: dict | None = None,
    execution_phase: str = "planning",
) -> str:
    """Insert a minimal TaskPacketRow. Returns task_packet_id."""
    from pearl.db.models.task_packet import TaskPacketRow

    tp_id = generate_id("tp")
    row = TaskPacketRow(
        task_packet_id=tp_id,
        project_id=project_id,
        environment="sandbox",
        packet_data={},
        trace_id=generate_id("trc"),
        outcome=outcome,
        execution_phase=execution_phase,
    )
    db_session.add(row)
    await db_session.commit()
    return tp_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_aggregates_cost_entries(db_session):
    """Three cost entries are aggregated: total_cost, models_used deduped, tools union."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")

    await _create_cost_entry(
        db_session, frun_id, pid,
        cost_usd=0.10, model="claude-3-sonnet", tools_called=["bash", "read"],
    )
    await _create_cost_entry(
        db_session, frun_id, pid,
        cost_usd=0.20, model="claude-3-opus", tools_called=["read", "write"],
    )
    await _create_cost_entry(
        db_session, frun_id, pid,
        cost_usd=0.15, model="claude-3-sonnet", tools_called=["bash"],
    )

    result = await materialize_run(
        frun_id=frun_id,
        task_packet_id=None,
        project_id=pid,
        session=db_session,
    )
    await db_session.commit()

    assert result == frun_id

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is not None
    assert abs(row.total_cost_usd - 0.45) < 1e-9
    assert row.models_used == ["claude-3-opus", "claude-3-sonnet"]  # sorted, deduped
    assert row.tools_called == ["bash", "read", "write"]  # sorted union


@pytest.mark.asyncio
async def test_idempotent_upsert(db_session):
    """Calling materialize_run twice with same frun_id produces exactly one row."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository
    from sqlalchemy import func, select
    from pearl.db.models.factory_run_summary import FactoryRunSummaryRow

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")

    await _create_cost_entry(db_session, frun_id, pid, cost_usd=0.05)

    # First call
    await materialize_run(
        frun_id=frun_id, task_packet_id=None, project_id=pid, session=db_session
    )
    await db_session.commit()

    # Second call — update cost entry then call again
    await _create_cost_entry(db_session, frun_id, pid, cost_usd=0.10)
    await materialize_run(
        frun_id=frun_id, task_packet_id=None, project_id=pid, session=db_session
    )
    await db_session.commit()

    count_stmt = select(func.count()).select_from(
        select(FactoryRunSummaryRow)
        .where(FactoryRunSummaryRow.frun_id == frun_id)
        .subquery()
    )
    count_result = await db_session.execute(count_stmt)
    count = count_result.scalar()
    assert count == 1

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    # Second call aggregated both entries: 0.05 + 0.10
    assert abs(row.total_cost_usd - 0.15) < 1e-9


@pytest.mark.asyncio
async def test_outcome_completed_maps_to_achieved(db_session):
    """Task packet with outcome.status='completed' produces outcome='achieved'."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")
    tp_id = await _create_task_packet(db_session, pid, outcome={"status": "completed"})

    await _create_cost_entry(db_session, frun_id, pid)

    await materialize_run(
        frun_id=frun_id, task_packet_id=tp_id, project_id=pid, session=db_session
    )
    await db_session.commit()

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is not None
    assert row.outcome == "achieved"


@pytest.mark.asyncio
async def test_outcome_failed_maps_to_failed(db_session):
    """Task packet with outcome.status='failed' produces outcome='failed'."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")
    tp_id = await _create_task_packet(db_session, pid, outcome={"status": "failed"})

    await _create_cost_entry(db_session, frun_id, pid)

    await materialize_run(
        frun_id=frun_id, task_packet_id=tp_id, project_id=pid, session=db_session
    )
    await db_session.commit()

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is not None
    assert row.outcome == "failed"


@pytest.mark.asyncio
async def test_no_outcome_falls_back_to_abandoned(db_session):
    """No task packet → outcome defaults to 'abandoned'."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")

    await _create_cost_entry(db_session, frun_id, pid)

    await materialize_run(
        frun_id=frun_id, task_packet_id=None, project_id=pid, session=db_session
    )
    await db_session.commit()

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is not None
    assert row.outcome == "abandoned"


@pytest.mark.asyncio
async def test_anomaly_flags_from_open_drift_findings(db_session):
    """Open drift findings are reflected in anomaly_flags."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository
    from pearl.db.models.finding import FindingRow

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")

    finding = FindingRow(
        finding_id=generate_id("find"),
        project_id=pid,
        environment="sandbox",
        category="drift_acute",
        severity="high",
        title="Unexpected tool invocation outside policy",
        source={"tool_name": "scanner", "tool_type": "drift", "trust_label": "trusted"},
        full_data={},
        detected_at=datetime.now(timezone.utc),
        status="open",
        anomaly_code="ANO_001",
    )
    db_session.add(finding)
    await db_session.commit()

    await _create_cost_entry(db_session, frun_id, pid)

    await materialize_run(
        frun_id=frun_id, task_packet_id=None, project_id=pid, session=db_session
    )
    await db_session.commit()

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is not None
    assert len(row.anomaly_flags) >= 1
    assert any("ANO_001" in flag for flag in row.anomaly_flags)


@pytest.mark.asyncio
async def test_no_entries_no_packet_returns_none(db_session):
    """No cost entries AND no task_packet_id → returns None, no row written."""
    from pearl.services.factory_run.materializer import materialize_run
    from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository

    pid = await _create_project(db_session)
    frun_id = generate_id("frun")

    result = await materialize_run(
        frun_id=frun_id, task_packet_id=None, project_id=pid, session=db_session
    )

    assert result is None

    row = await FactoryRunSummaryRepository(db_session).get(frun_id)
    assert row is None
