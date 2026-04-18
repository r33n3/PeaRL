"""Tests for gate re-evaluation behavior on task packet completion.

CLAUDE.md governance constraint:
- Manual gate (auto_pass=False): re-eval failure must propagate (raise → 500)
- Auto-elevation gate (auto_pass=True): re-eval failure must log warning, not raise (200)
"""
import pytest
from unittest.mock import patch, MagicMock

from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.id_generator import generate_id


async def _create_project(client, project_id: str) -> str:
    r = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": project_id,
            "name": f"Gate reeval test {project_id}",
            "description": "Gate re-eval behavior test",
            "owner_team": "test-team",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": False,
        },
    )
    assert r.status_code == 201, r.text
    return project_id


async def _create_and_claim_packet(db_session, project_id: str) -> str:
    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(db_session)
    await repo.create(
        task_packet_id=tp_id,
        project_id=project_id,
        environment="sandbox",
        trace_id=generate_id("trace_"),
        packet_data={
            "task_type": "remediate_gate_blocker",
            "task_packet_id": tp_id,
            "status": "claimed",
            "rule_id": generate_id("rule_"),
            "rule_type": "test_rule",
            "fix_guidance": "Fix it",
            "transition": "sandbox->dev",
            "created_by": "test",
        },
    )
    row = await repo.get(tp_id)
    row.status = "claimed"
    row.agent_id = "test-agent"
    await db_session.commit()
    return tp_id


@pytest.mark.asyncio
async def test_gate_reeval_failure_raises_in_manual_mode(client, db_session):
    """Manual gate (auto_pass=False): re-eval failure must return 500."""
    pid = await _create_project(client, "proj_reeval_manual")
    tp_id = await _create_and_claim_packet(db_session, pid)

    with patch(
        "pearl.services.promotion.gate_evaluator.evaluate_promotion",
        side_effect=RuntimeError("gate evaluator exploded"),
    ):
        r = await client.post(
            f"/api/v1/task-packets/{tp_id}/complete",
            json={"status": "completed", "fix_summary": "done"},
        )

    # Currently code swallows exception (line 344: except Exception: pass)
    # After fix, must return 500 for manual gate failure
    assert r.status_code == 500, (
        f"Expected 500 for manual gate re-eval failure, got {r.status_code}: {r.text}"
    )


@pytest.mark.asyncio
async def test_gate_reeval_failure_logs_warning_in_auto_mode(client, db_session):
    """Auto gate (auto_pass=True): re-eval failure must return 200 and log a warning.

    After the fix, a logger import will be added to task_packets.py and a warning
    will be logged on gate re-eval failure in auto mode. This test verifies that:
    1. Response is 200 (task completes successfully despite gate failure)
    2. logger.warning is called with appropriate context
    """
    pid = await _create_project(client, "proj_reeval_auto")
    tp_id = await _create_and_claim_packet(db_session, pid)

    with patch(
        "pearl.services.promotion.gate_evaluator.evaluate_promotion",
        side_effect=RuntimeError("gate evaluator exploded"),
    ):
        # Import and patch logger in task_packets module (after fix)
        import pearl.api.routes.task_packets as tp_module
        original_logger = getattr(tp_module, "logger", None)
        mock_logger = MagicMock()
        tp_module.logger = mock_logger

        try:
            r = await client.post(
                f"/api/v1/task-packets/{tp_id}/complete",
                json={"status": "completed", "fix_summary": "done"},
            )
        finally:
            # Restore original logger state
            if original_logger is not None:
                tp_module.logger = original_logger
            elif hasattr(tp_module, "logger"):
                delattr(tp_module, "logger")

    # After fix: must return 200 for auto gate failure (with warning logged)
    assert r.status_code == 200, (
        f"Expected 200 for auto gate re-eval failure, got {r.status_code}: {r.text}"
    )

    # After fix: logger.warning should be called when gate re-eval fails in auto mode
    mock_logger.warning.assert_called_once()
