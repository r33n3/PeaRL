"""Integration tests for AgentCore routes (/api/v1/agentcore/*)."""

import pytest


@pytest.mark.asyncio
async def test_list_deployments_empty(client):
    resp = await client.get("/api/v1/agentcore/deployments?org_id=org_test")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_latest_deployment_not_found(client):
    resp = await client.get("/api/v1/agentcore/deployments/latest?org_id=org_missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_scan_state_not_found(client):
    resp = await client.get("/api/v1/agentcore/scan-state?org_id=org_missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_deploy_requires_org_id(reviewer_client):
    # reviewer_client has all roles including admin
    resp = await reviewer_client.post("/api/v1/agentcore/deploy", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_trigger_deploy_enqueues_job(reviewer_client):
    resp = await reviewer_client.post(
        "/api/v1/agentcore/deploy",
        json={
            "org_id": "org_test",
            "agent_aliases": [],
            "blocked_rules": [],
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["job_id"].startswith("job_")


@pytest.mark.asyncio
async def test_trigger_deploy_job_retrievable(reviewer_client):
    deploy_resp = await reviewer_client.post(
        "/api/v1/agentcore/deploy",
        json={"org_id": "org_test"},
    )
    job_id = deploy_resp.json()["job_id"]

    job_resp = await reviewer_client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    body = job_resp.json()
    assert body["job_type"] == "export_cedar_policies"
    assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_list_deployments_after_create(client, db_session):
    """Seed a deployment row and verify the list endpoint returns it."""
    from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository

    repo = CedarDeploymentRepository(db_session)
    await repo.create(
        deployment_id="cdep_test001",
        org_id="org_with_deploy",
        gateway_arn="arn:test",
        bundle_hash="deadbeef" * 8,
        bundle_snapshot={"policies": {"static": {}}},
        status="active",
        deployed_by="usr_admin",
        triggered_by="manual",
    )
    await db_session.commit()

    resp = await client.get("/api/v1/agentcore/deployments?org_id=org_with_deploy")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["deployment_id"] == "cdep_test001"
    assert data[0]["status"] == "active"


@pytest.mark.asyncio
async def test_get_latest_deployment_after_create(client, db_session):
    from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository

    repo = CedarDeploymentRepository(db_session)
    await repo.create(
        deployment_id="cdep_latest",
        org_id="org_latest",
        gateway_arn="arn:latest",
        bundle_hash="cafebabe" * 8,
        bundle_snapshot={"policies": {"static": {}}},
        status="active",
        deployed_by="usr_admin",
        triggered_by="approval",
    )
    await db_session.commit()

    resp = await client.get("/api/v1/agentcore/deployments/latest?org_id=org_latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment_id"] == "cdep_latest"
    assert body["bundle_hash"] == "cafebabe" * 8


@pytest.mark.asyncio
async def test_get_scan_state_after_upsert(client, db_session):
    from datetime import datetime, timezone
    from pearl.repositories.agentcore_scan_state_repo import AgentCoreScanStateRepository

    repo = AgentCoreScanStateRepository(db_session)
    await repo.upsert(
        org_id="org_scan_state",
        last_scan_findings_count=3,
        last_scan_entries_processed=42,
        baseline_call_rate=10.5,
    )
    await db_session.commit()

    resp = await client.get("/api/v1/agentcore/scan-state?org_id=org_scan_state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["org_id"] == "org_scan_state"
    assert body["last_scan_findings_count"] == 3
    assert body["last_scan_entries_processed"] == 42
    assert body["baseline_call_rate"] == pytest.approx(10.5)
