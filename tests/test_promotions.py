"""Tests for promotion evaluate_promotion_readiness route edge cases."""

import pytest


@pytest.mark.asyncio
async def test_evaluate_aiuc_enrichment_failure_surfaces_error(client):
    """When AIUC enrichment raises, response must include aiuc_compliance.error — not an absent key."""
    from unittest.mock import patch

    resp = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": "proj_aiuc_error_test",
            "name": "AIUC Error Test Project",
            "owner_team": "test-team",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": True,
        },
        headers={"X-API-Key": "pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"},
    )
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    with patch(
        "pearl.api.routes.promotions._build_eval_context",
        side_effect=RuntimeError("injected aiuc failure"),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project_id}/promotions/evaluate",
            json={"source_environment": "pilot", "target_environment": "dev"},
            headers={"X-API-Key": "pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"},
        )

    assert resp.status_code == 200  # evaluation itself succeeds
    body = resp.json()
    assert "aiuc_compliance" in body, "aiuc_compliance key must always be present"
    assert body["aiuc_compliance"].get("error") == "enrichment_failed"
