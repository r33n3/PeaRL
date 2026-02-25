"""Contract tests for approval and exception workflows."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_create_approval_request_contract(client):
    """POST /approvals/requests returns 201 with pending status."""
    req = load_example("approvals/create-approval.request.json")
    r = await client.post("/api/v1/approvals/requests", json=req)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["approval_request_id"] == req["approval_request_id"]


@pytest.mark.asyncio
async def test_approval_decision_contract(client):
    """POST /approvals/{id}/decide transitions status to approved."""
    # Create approval first
    req = load_example("approvals/create-approval.request.json")
    await client.post("/api/v1/approvals/requests", json=req)

    # Decide
    decision = load_example("approvals/decision.request.json")
    r = await client.post(
        f"/api/v1/approvals/{req['approval_request_id']}/decide", json=decision
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "approve"
    assert "decided_by" in body


@pytest.mark.asyncio
async def test_approval_already_decided(client):
    """Deciding on an already-decided approval returns 409."""
    req = load_example("approvals/create-approval.request.json")
    await client.post("/api/v1/approvals/requests", json=req)

    decision = load_example("approvals/decision.request.json")
    await client.post(
        f"/api/v1/approvals/{req['approval_request_id']}/decide", json=decision
    )

    # Try to decide again
    r = await client.post(
        f"/api/v1/approvals/{req['approval_request_id']}/decide", json=decision
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_exception_contract(client):
    """POST /exceptions returns 201 with active status."""
    req = load_example("exceptions/create-exception.request.json")
    r = await client.post("/api/v1/exceptions", json=req)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"
    assert body["exception_id"] == req["exception_id"]
