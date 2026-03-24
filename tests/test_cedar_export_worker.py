"""Integration tests for CedarExportWorker and CloudWatchScanWorker (dry-run mode)."""

import pytest

from pearl.workers.cedar_export_worker import CedarExportWorker
from pearl.workers.cloudwatch_scan_worker import CloudWatchScanWorker


# ── CedarExportWorker ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cedar_export_worker_requires_org_id(db_session):
    worker = CedarExportWorker()
    with pytest.raises(ValueError, match="org_id"):
        await worker.process("job_test", {}, db_session)


@pytest.mark.asyncio
async def test_cedar_export_worker_dry_run_creates_deployment(db_session):
    """Worker runs in dry-run mode (no gateway_arn configured) and persists a row."""
    worker = CedarExportWorker()
    result = await worker.process(
        "job_dry001",
        {
            "org_id": "org_dry_run",
            "triggered_by": "manual",
            "deployed_by": "usr_test",
        },
        db_session,
    )
    refs = result["result_refs"]
    assert len(refs) == 1
    ref = refs[0]
    assert ref["kind"] == "cedar_deployment"
    assert ref["status"] == "active"
    assert ref["bundle_hash"]
    assert ref["agentcore_deployment_id"].startswith("dryrun_")


@pytest.mark.asyncio
async def test_cedar_export_worker_persists_deployment_row(db_session):
    from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository

    worker = CedarExportWorker()
    result = await worker.process(
        "job_persist001",
        {"org_id": "org_persist_test", "triggered_by": "manual"},
        db_session,
    )
    deployment_id = result["result_refs"][0]["ref_id"]

    repo = CedarDeploymentRepository(db_session)
    row = await repo.get(deployment_id)
    assert row is not None
    assert row.org_id == "org_persist_test"
    assert row.status == "active"
    assert row.triggered_by == "manual"
    assert row.bundle_snapshot is not None


@pytest.mark.asyncio
async def test_cedar_export_worker_skips_unchanged_bundle(db_session):
    """Second run with same governance state returns 'skipped'."""
    worker = CedarExportWorker()
    payload = {"org_id": "org_skip_test", "triggered_by": "manual"}

    result1 = await worker.process("job_skip001", payload, db_session)
    assert result1["result_refs"][0]["status"] == "active"

    result2 = await worker.process("job_skip002", payload, db_session)
    assert result2["result_refs"][0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_cedar_export_worker_supersedes_old_active(db_session):
    """After a new deploy, the old active row is superseded."""
    from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository

    worker = CedarExportWorker()
    # First deploy
    r1 = await worker.process(
        "job_sup001",
        {"org_id": "org_supersede", "triggered_by": "manual"},
        db_session,
    )
    dep1_id = r1["result_refs"][0]["ref_id"]

    # Second deploy with different governance state (add a blocking rule)
    r2 = await worker.process(
        "job_sup002",
        {
            "org_id": "org_supersede",
            "triggered_by": "manual",
            "blocked_rules": ["critical_findings_zero"],
        },
        db_session,
    )
    dep2_id = r2["result_refs"][0]["ref_id"]

    repo = CedarDeploymentRepository(db_session)
    dep1 = await repo.get(dep1_id)
    dep2 = await repo.get(dep2_id)

    assert dep1.status == "superseded"
    assert dep2.status == "active"


@pytest.mark.asyncio
async def test_cedar_export_worker_includes_policy_count(db_session):
    worker = CedarExportWorker()
    result = await worker.process(
        "job_count001",
        {"org_id": "org_count", "triggered_by": "manual"},
        db_session,
    )
    assert result["result_refs"][0]["policy_count"] >= 1


@pytest.mark.asyncio
async def test_cedar_export_worker_with_agent_aliases(db_session):
    from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository

    worker = CedarExportWorker()
    result = await worker.process(
        "job_alias001",
        {
            "org_id": "org_alias_test",
            "triggered_by": "manual",
            "agent_aliases": [
                {"alias_id": "alias_prod_1", "environment": "prod"},
            ],
        },
        db_session,
    )
    ref = result["result_refs"][0]
    assert ref["status"] == "active"

    repo = CedarDeploymentRepository(db_session)
    row = await repo.get(ref["ref_id"])
    static = row.bundle_snapshot["policies"]["static"]
    alias_keys = [k for k in static if "alias_prod_1" in k]
    assert len(alias_keys) == 1


# ── CloudWatchScanWorker ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cloudwatch_scan_worker_requires_org_id(db_session):
    worker = CloudWatchScanWorker()
    with pytest.raises(ValueError, match="org_id"):
        await worker.process("job_cw_test", {}, db_session)


@pytest.mark.asyncio
async def test_cloudwatch_scan_worker_dry_run_no_findings(db_session):
    """With no log_group_arn configured, worker returns zero findings."""
    worker = CloudWatchScanWorker()
    result = await worker.process(
        "job_cw_dry",
        {"org_id": "org_cw_dry", "project_id": None},
        db_session,
    )
    refs = result["result_refs"]
    assert len(refs) == 1
    assert refs[0]["entries_processed"] == 0
    assert refs[0]["findings_accepted"] == 0
    assert refs[0]["anomalies"] == []


@pytest.mark.asyncio
async def test_cloudwatch_scan_worker_updates_scan_state(db_session):
    """After a dry-run scan, the AgentCoreScanState row is created/updated."""
    from pearl.repositories.agentcore_scan_state_repo import AgentCoreScanStateRepository

    worker = CloudWatchScanWorker()
    await worker.process(
        "job_cw_state",
        {"org_id": "org_cw_state"},
        db_session,
    )

    repo = AgentCoreScanStateRepository(db_session)
    state = await repo.get_for_org("org_cw_state")
    assert state is not None
    assert state.last_scan_job_id == "job_cw_state"
    assert state.last_scan_entries_processed == 0


@pytest.mark.asyncio
async def test_cloudwatch_scan_worker_idempotent_state_update(db_session):
    """Running the worker twice updates the scan state correctly."""
    from pearl.repositories.agentcore_scan_state_repo import AgentCoreScanStateRepository

    worker = CloudWatchScanWorker()
    await worker.process("job_cw_idem1", {"org_id": "org_cw_idem"}, db_session)
    await worker.process("job_cw_idem2", {"org_id": "org_cw_idem"}, db_session)

    repo = AgentCoreScanStateRepository(db_session)
    state = await repo.get_for_org("org_cw_idem")
    assert state.last_scan_job_id == "job_cw_idem2"
