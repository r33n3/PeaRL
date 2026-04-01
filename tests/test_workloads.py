"""Tests for the Workload Registry.

Covers:
- POST /workloads/register creates a workload, returns 201
- POST /workloads/{svid}/heartbeat updates last_seen_at, returns 200
- POST /workloads/{svid}/heartbeat returns 404 for unknown SVID
- POST /workloads/{svid}/heartbeat returns 404 for inactive workload
- DELETE /workloads/{svid} deactivates workload, returns 200
- DELETE /workloads/{svid} returns 404 for unknown SVID
- GET /workloads defaults to active-only list
- GET /workloads?status=all returns active and inactive
- Workloads not seen for >5 minutes are auto-marked inactive on read
- GET /dashboard/metrics includes active_workload_count
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_register_payload(svid: str, tp_id: str = "tp_test001") -> dict:
    return {
        "svid": svid,
        "task_packet_id": tp_id,
        "allowance_profile_id": "alp_test001",
        "agent_id": "agent_test001",
    }


# ---------------------------------------------------------------------------
# POST /workloads/register
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_workload_returns_201(reviewer_client):
    """Registering a new SVID creates a workload and returns 201."""
    payload = _make_register_payload("spiffe://factory/agent/worker-1")
    r = await reviewer_client.post("/api/v1/workloads/register", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["svid"] == "spiffe://factory/agent/worker-1"
    assert data["status"] == "active"
    assert "workload_id" in data
    assert data["workload_id"].startswith("wkld_")
    assert "registered_at" in data


@pytest.mark.asyncio
async def test_register_workload_persists_fields(reviewer_client, db_session):
    """Registered workload has all fields stored in the DB."""
    from pearl.db.models.workload import WorkloadRow
    from sqlalchemy import select

    svid = "spiffe://factory/agent/worker-persist"
    payload = _make_register_payload(svid, tp_id="tp_persist")
    r = await reviewer_client.post("/api/v1/workloads/register", json=payload)
    assert r.status_code == 201

    result = await db_session.execute(
        select(WorkloadRow).where(WorkloadRow.svid == svid)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.task_packet_id == "tp_persist"
    assert row.allowance_profile_id == "alp_test001"
    assert row.agent_id == "agent_test001"
    assert row.status == "active"


@pytest.mark.asyncio
async def test_register_duplicate_svid_returns_409(reviewer_client):
    """Registering the same SVID twice returns 409 Conflict."""
    svid = "spiffe://factory/agent/duplicate"
    payload = _make_register_payload(svid)
    r1 = await reviewer_client.post("/api/v1/workloads/register", json=payload)
    assert r1.status_code == 201

    r2 = await reviewer_client.post("/api/v1/workloads/register", json=payload)
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# POST /workloads/{svid}/heartbeat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_updates_last_seen_at(reviewer_client, db_session):
    """Heartbeat updates last_seen_at on an active workload."""
    svid = "spiffe://factory/agent/heartbeat-ok"
    r = await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))
    assert r.status_code == 201
    workload_id = r.json()["workload_id"]

    hb_r = await reviewer_client.post(f"/api/v1/workloads/{svid}/heartbeat")
    assert hb_r.status_code == 200
    data = hb_r.json()
    assert data["workload_id"] == workload_id
    assert "last_seen_at" in data


@pytest.mark.asyncio
async def test_heartbeat_unknown_svid_returns_404(reviewer_client):
    """Heartbeat for an unknown SVID returns 404."""
    svid = "spiffe://factory/agent/unknown-hb"
    r = await reviewer_client.post(f"/api/v1/workloads/{svid}/heartbeat", follow_redirects=True)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_inactive_svid_returns_404(reviewer_client, db_session):
    """Heartbeat for an inactive workload returns 404."""
    svid = "spiffe://factory/agent/hb-inactive"
    r = await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))
    assert r.status_code == 201

    del_r = await reviewer_client.delete(f"/api/v1/workloads/{svid}")
    assert del_r.status_code == 200

    hb_r = await reviewer_client.post(f"/api/v1/workloads/{svid}/heartbeat")
    assert hb_r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /workloads/{svid}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deregister_sets_status_inactive(reviewer_client, db_session):
    """DELETE /workloads/{svid} sets status to inactive in the DB."""
    from pearl.db.models.workload import WorkloadRow
    from sqlalchemy import select

    svid = "spiffe://factory/agent/deregister-me"
    r = await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))
    assert r.status_code == 201

    del_r = await reviewer_client.delete(f"/api/v1/workloads/{svid}")
    assert del_r.status_code == 200

    result = await db_session.execute(
        select(WorkloadRow).where(WorkloadRow.svid == svid)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.status == "inactive"


@pytest.mark.asyncio
async def test_deregister_unknown_svid_returns_404(reviewer_client):
    """DELETE for an unknown SVID returns 404."""
    svid = "spiffe://factory/agent/nobody"
    r = await reviewer_client.delete(f"/api/v1/workloads/{svid}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /workloads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_workloads_returns_active_by_default(reviewer_client):
    """GET /workloads returns only active workloads by default."""
    svid_active = "spiffe://factory/agent/list-active"
    svid_inactive = "spiffe://factory/agent/list-inactive"

    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid_active))
    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid_inactive))
    await reviewer_client.delete(f"/api/v1/workloads/{svid_inactive}")

    r = await reviewer_client.get("/api/v1/workloads")
    assert r.status_code == 200
    data = r.json()
    svids = [w["svid"] for w in data]
    assert svid_active in svids
    assert svid_inactive not in svids


@pytest.mark.asyncio
async def test_list_workloads_status_all_includes_inactive(reviewer_client):
    """GET /workloads?status=all includes both active and inactive."""
    svid_active = "spiffe://factory/agent/all-active"
    svid_inactive = "spiffe://factory/agent/all-inactive"

    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid_active))
    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid_inactive))
    await reviewer_client.delete(f"/api/v1/workloads/{svid_inactive}")

    r = await reviewer_client.get("/api/v1/workloads?status=all")
    assert r.status_code == 200
    data = r.json()
    svids = [w["svid"] for w in data]
    assert svid_active in svids
    assert svid_inactive in svids


@pytest.mark.asyncio
async def test_list_workloads_response_shape(reviewer_client):
    """GET /workloads entries include required fields."""
    svid = "spiffe://factory/agent/shape-check"
    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))

    r = await reviewer_client.get("/api/v1/workloads")
    assert r.status_code == 200
    data = r.json()
    entry = next((w for w in data if w["svid"] == svid), None)
    assert entry is not None
    assert "workload_id" in entry
    assert "svid" in entry
    assert "task_packet_id" in entry
    assert "allowance_profile_id" in entry
    assert "status" in entry
    assert "last_seen_at" in entry


# ---------------------------------------------------------------------------
# Inactive timeout (on-read approach)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stale_workload_auto_marked_inactive(reviewer_client, db_session):
    """Workload not seen for >5 minutes is marked inactive when listing active."""
    from pearl.db.models.workload import WorkloadRow
    from sqlalchemy import select

    svid = "spiffe://factory/agent/stale-one"
    r = await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))
    assert r.status_code == 201

    # Manually backdate last_seen_at to 6 minutes ago
    result = await db_session.execute(
        select(WorkloadRow).where(WorkloadRow.svid == svid)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    await db_session.commit()

    # GET /workloads (active only) should not include the stale workload
    list_r = await reviewer_client.get("/api/v1/workloads")
    assert list_r.status_code == 200
    data = list_r.json()
    svids = [w["svid"] for w in data]
    assert svid not in svids

    # Verify the DB row was updated to inactive
    await db_session.refresh(row)
    assert row.status == "inactive"


# ---------------------------------------------------------------------------
# Dashboard active_workload_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_metrics_includes_active_workload_count(client):
    """GET /dashboard/metrics includes active_workload_count."""
    r = await client.get("/api/v1/dashboard/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "active_workload_count" in data
    assert isinstance(data["active_workload_count"], int)


@pytest.mark.asyncio
async def test_dashboard_metrics_active_workload_count_reflects_registrations(reviewer_client, client):
    """active_workload_count increases after registration and decreases after deregister."""
    r0 = await client.get("/api/v1/dashboard/metrics")
    baseline = r0.json()["active_workload_count"]

    svid = "spiffe://factory/agent/dashboard-count"
    await reviewer_client.post("/api/v1/workloads/register", json=_make_register_payload(svid))

    r1 = await client.get("/api/v1/dashboard/metrics")
    assert r1.json()["active_workload_count"] == baseline + 1

    await reviewer_client.delete(f"/api/v1/workloads/{svid}")

    r2 = await client.get("/api/v1/dashboard/metrics")
    assert r2.json()["active_workload_count"] == baseline
