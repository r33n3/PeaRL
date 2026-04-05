"""Contract tests for findings ingestion and remediation generation."""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_compiled_project(client):
    """Full project setup through compilation."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    pid = project["project_id"]

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)
    return pid


@pytest.mark.asyncio
async def test_findings_ingest_contract(client):
    """POST /findings/ingest accepts findings with partial acceptance support."""
    req = load_example("findings/findings-ingest.request.json")
    r = await client.post("/api/v1/findings/ingest", json=req)
    assert r.status_code == 202
    body = r.json()
    assert "accepted_count" in body
    assert "quarantined_count" in body
    assert "batch_id" in body
    assert body["accepted_count"] >= 1


@pytest.mark.asyncio
async def test_remediation_spec_contract(client):
    """POST remediation-specs/generate returns a valid remediation spec."""
    pid = await _setup_compiled_project(client)

    # Ingest findings first
    findings_req = load_example("findings/findings-ingest.request.json")
    await client.post("/api/v1/findings/ingest", json=findings_req)

    # Generate remediation spec
    rem_req = load_example("remediation/generate-remediation-spec.request.json")
    r = await client.post(
        f"/api/v1/projects/{pid}/remediation-specs/generate", json=rem_req
    )
    assert r.status_code == 201
    body = r.json()
    assert body["eligibility"] in ("auto_allowed", "auto_allowed_with_approval", "human_required")
    assert "approval_required" in body
    assert "required_tests" in body
    assert len(body["required_tests"]) > 0
    assert "risk_summary" in body


@pytest.mark.asyncio
async def test_quarantine_logs_warning_on_db_failure(client, caplog):
    """Quarantined findings must emit a WARNING log with finding_id."""
    from pearl.config import settings
    from pearl.repositories.finding_repo import FindingRepository

    # Enable local_mode so get_current_user returns a synthetic user (no JWT needed)
    original_local = settings.local_mode
    settings.local_mode = True

    # Patch FindingRepository.create to raise on the second call (simulated DB error)
    original_create = FindingRepository.create
    call_count = 0

    async def failing_create(self, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise Exception("simulated DB constraint violation")
        return await original_create(self, **kwargs)

    req = {
        "schema_version": "1.0",
        "source_batch": {
            "batch_id": "batch_quarantine_test",
            "source_system": "test_scanner",
            "received_at": "2026-01-01T00:00:00Z",
            "trust_label": "trusted_internal",
        },
        "findings": [
            {
                "schema_version": "1.0",
                "finding_id": "find_qtest001",
                "project_id": "proj_test001",
                "environment": "dev",
                "category": "security",
                "severity": "high",
                "title": "Test finding one",
                "detected_at": "2026-01-01T00:00:00Z",
                "status": "open",
                "source": {
                    "tool_name": "test_tool",
                    "tool_type": "sast",
                    "trust_label": "trusted_internal",
                },
            },
            {
                "schema_version": "1.0",
                "finding_id": "find_qtest002",
                "project_id": "proj_test001",
                "environment": "dev",
                "category": "security",
                "severity": "low",
                "title": "Test finding two",
                "detected_at": "2026-01-01T00:00:00Z",
                "status": "open",
                "source": {
                    "tool_name": "test_tool",
                    "tool_type": "sast",
                    "trust_label": "trusted_internal",
                },
            },
        ],
    }

    try:
        with patch.object(FindingRepository, "create", failing_create):
            with caplog.at_level(logging.WARNING, logger="pearl.api.routes.findings"):
                r = await client.post("/api/v1/findings/ingest", json=req)
    finally:
        settings.local_mode = original_local

    assert r.status_code == 202
    body = r.json()
    assert body["quarantined_count"] >= 1

    warning_records = [rec for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert any(
        "quarantine" in r.message.lower() for r in warning_records
    ), f"Expected quarantine WARNING log, got: {[r.message for r in warning_records]}"
    assert any(
        getattr(r, "finding_id", None) == "find_qtest002" for r in warning_records
    ), f"Expected finding_id='find_qtest002' in log record attributes, got records: {[vars(r) for r in warning_records]}"
