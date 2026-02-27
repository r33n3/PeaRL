"""Tests for the project timeline endpoint.

Covers:
- GET /projects/{id}/timeline returns 200 with a list for an existing project
- 404 returned for non-existent project
- Results are sorted by timestamp descending
- Timeline is empty for a brand-new project with no activity
- After seeding a finding, the timeline includes a "finding_detected" event
- After a gate evaluation, the timeline includes a "gate_evaluated" event
- After completing a task packet, the timeline includes an "agent_fixed" event
- Duplicate event IDs are deduplicated
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

async def _create_project(client, project_id: str, ai_enabled: bool = False) -> str:
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = ai_enabled
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201
    return project_id


async def _setup_full_project(client, project_id: str, ai_enabled: bool = False) -> str:
    await _create_project(client, project_id, ai_enabled)

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
async def test_timeline_not_found(client):
    """GET /projects/{id}/timeline returns 404 for an unknown project."""
    r = await client.get("/api/v1/projects/proj_nonexistent_timeline/timeline")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_timeline_returns_200(client):
    """GET /projects/{id}/timeline returns 200 for an existing project."""
    pid = await _create_project(client, "proj_timeline_200")
    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_timeline_returns_list(client):
    """GET /projects/{id}/timeline returns a list (possibly empty)."""
    pid = await _create_project(client, "proj_timeline_list")
    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_timeline_empty_for_new_project(client):
    """A brand-new project with no activity has an empty timeline."""
    pid = await _create_project(client, "proj_timeline_empty")
    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_timeline_includes_finding_detected_event(client):
    """After ingesting a finding, the timeline includes a 'finding_detected' event."""
    pid = await _create_project(client, "proj_timeline_finding")

    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_timeline_001"
    findings_req["findings"][0]["severity"] = "high"
    ingest_r = await client.post("/api/v1/findings/ingest", json=findings_req)
    assert ingest_r.status_code in (200, 201, 202)

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    assert r.status_code == 200
    events = r.json()

    event_types = [e["event_type"] for e in events]
    assert "finding_detected" in event_types

    finding_events = [e for e in events if e["event_type"] == "finding_detected"]
    assert len(finding_events) >= 1

    ev = finding_events[0]
    assert "event_id" in ev
    assert "timestamp" in ev
    assert "summary" in ev
    assert ev["event_id"].startswith("finding_")


@pytest.mark.asyncio
async def test_timeline_sorted_descending(client):
    """Timeline events are sorted by timestamp descending (newest first)."""
    pid = await _setup_full_project(client, "proj_timeline_sort")

    # Ingest a finding to seed at least one event
    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_sort_001"
    await client.post("/api/v1/findings/ingest", json=findings_req)

    # Run an evaluation to add another event
    await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()

    if len(events) >= 2:
        for i in range(len(events) - 1):
            ts_current = events[i]["timestamp"]
            ts_next = events[i + 1]["timestamp"]
            assert ts_current >= ts_next, (
                f"Timeline not sorted descending at index {i}: "
                f"{ts_current} < {ts_next}"
            )


@pytest.mark.asyncio
async def test_timeline_includes_gate_evaluated_event(client):
    """After a gate evaluation, the timeline includes a 'gate_evaluated' event."""
    pid = await _setup_full_project(client, "proj_timeline_gate_eval")

    eval_r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert eval_r.status_code == 200

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()

    gate_events = [e for e in events if e["event_type"] == "gate_evaluated"]
    assert len(gate_events) >= 1

    ev = gate_events[0]
    assert ev["event_id"].startswith("eval_")
    assert "evaluation_id" in ev
    assert ev["evaluation_id"] is not None


@pytest.mark.asyncio
async def test_timeline_event_structure(client):
    """Timeline events have the required common fields."""
    pid = await _setup_full_project(client, "proj_timeline_struct")

    await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()
    assert len(events) > 0

    required_fields = ["event_id", "event_type", "timestamp", "summary"]
    for ev in events:
        for field in required_fields:
            assert field in ev, f"Event missing required field '{field}': {ev}"


@pytest.mark.asyncio
async def test_timeline_no_duplicate_event_ids(client):
    """All event IDs in the timeline are unique (deduplicated)."""
    pid = await _setup_full_project(client, "proj_timeline_dedup")

    # Add multiple events
    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_dedup_001"
    await client.post("/api/v1/findings/ingest", json=findings_req)

    await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()

    event_ids = [e["event_id"] for e in events]
    assert len(event_ids) == len(set(event_ids)), "Duplicate event IDs found in timeline"


@pytest.mark.asyncio
async def test_timeline_task_packet_created_event(client, db_session):
    """After creating a task packet, the timeline includes a 'task_packet_created' event."""
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    from pearl.services.id_generator import generate_id

    pid = await _create_project(client, "proj_timeline_tp_created")

    # Create a task packet directly in DB
    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(db_session)
    await repo.create(
        task_packet_id=tp_id,
        project_id=pid,
        environment="sandbox",
        trace_id=generate_id("trace_"),
        packet_data={
            "task_type": "remediate_gate_blocker",
            "task_packet_id": tp_id,
            "status": "pending",
            "rule_id": generate_id("rule_"),
            "rule_type": "test_rule",
        },
    )
    await db_session.commit()

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()

    tp_events = [e for e in events if e["event_type"] == "task_packet_created"]
    assert len(tp_events) >= 1
    assert tp_events[0]["event_id"].startswith("tp_created_")


@pytest.mark.asyncio
async def test_timeline_agent_fixed_event_after_completion(client, db_session):
    """After completing a task packet, the timeline includes an 'agent_fixed' event."""
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    from pearl.services.id_generator import generate_id

    pid = await _create_project(client, "proj_timeline_agent_fixed")

    # Create a task packet directly in DB
    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(db_session)
    await repo.create(
        task_packet_id=tp_id,
        project_id=pid,
        environment="sandbox",
        trace_id=generate_id("trace_"),
        packet_data={
            "task_type": "remediate_gate_blocker",
            "task_packet_id": tp_id,
            "status": "pending",
            "rule_id": generate_id("rule_"),
            "rule_type": "test_rule",
        },
    )
    await db_session.commit()

    # Claim and complete via API
    await client.post(f"/api/v1/task-packets/{tp_id}/claim", json={"agent_id": "agent_test_001"})
    await client.post(
        f"/api/v1/task-packets/{tp_id}/complete",
        json={
            "status": "completed",
            "fix_summary": "Fixed the issue",
            "commit_ref": "abc123",
            "files_changed": ["app.py"],
        },
    )

    r = await client.get(f"/api/v1/projects/{pid}/timeline")
    events = r.json()

    fixed_events = [e for e in events if e["event_type"] == "agent_fixed"]
    assert len(fixed_events) >= 1
    assert fixed_events[0]["event_id"].startswith("tp_completed_")

    detail = fixed_events[0].get("detail", {})
    assert detail.get("fix_summary") == "Fixed the issue"
    assert detail.get("commit_ref") == "abc123"
