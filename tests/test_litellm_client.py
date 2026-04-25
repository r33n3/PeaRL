"""Unit tests for LiteLLMClient — mocks all HTTP calls."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from pearl.integrations.litellm import LiteLLMClient, KeyDetails


def _make_client() -> LiteLLMClient:
    return LiteLLMClient(base_url="http://fake-litellm", api_key="test-key")


def _mock_key_info_response(overrides: dict | None = None) -> dict:
    """Minimal /key/info response matching the LiteLLM schema."""
    base = {
        "key_alias": "vk-orchestrator-frun58m",
        "team_id": "team-factory-01",
        "organization_id": "org-acme",
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "max_budget": 5.0,
        "spend": 1.23,
        "budget_reset_at": None,
        "tpm_limit": None,
        "rpm_limit": None,
        "object_permission": {
            "mcp_access_groups": ["PeaRL-prod", "github-tools"],
            "blocked_tools": ["PeaRL-pearl_approve_promotion"],
            "vector_stores": [],
            "mcp_tool_permissions": {},
        },
        "expires": None,
        "blocked": False,
        "last_active": "2026-04-25T10:00:00Z",
        "soft_budget_cooldown": False,
        "rotation_count": 0,
        "last_rotation_at": None,
        "created_at": "2026-04-01T00:00:00Z",
        "updated_at": "2026-04-25T10:00:00Z",
    }
    if overrides:
        base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_get_key_details_returns_parsed_model():
    """get_key_details parses all KeyDetails fields from /key/info response."""
    client = _make_client()
    raw = _mock_key_info_response()

    with patch.object(client, "_fetch_key_info", new=AsyncMock(return_value=raw)):
        details = await client.get_key_details("vk-orchestrator-frun58m")

    assert details is not None
    assert details.key_alias == "vk-orchestrator-frun58m"
    assert details.team_id == "team-factory-01"
    assert details.models == ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    assert details.max_budget == 5.0
    assert details.spend == 1.23
    assert details.blocked is False
    assert details.mcp_access_groups == ["PeaRL-prod", "github-tools"]
    assert details.blocked_tools == ["PeaRL-pearl_approve_promotion"]


@pytest.mark.asyncio
async def test_get_key_details_returns_none_on_404():
    """get_key_details returns None when LiteLLM returns 404."""
    import httpx
    client = _make_client()

    with patch.object(client, "_fetch_key_info", new=AsyncMock(side_effect=httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    ))):
        details = await client.get_key_details("nonexistent-alias")

    assert details is None


@pytest.mark.asyncio
async def test_get_key_details_returns_none_on_connect_error():
    """get_key_details returns None when LiteLLM is unreachable."""
    import httpx
    client = _make_client()

    with patch.object(client, "_fetch_key_info", new=AsyncMock(side_effect=httpx.ConnectError("unreachable"))):
        details = await client.get_key_details("any-alias")

    assert details is None


# Tests for check_key_lifecycle()

from pearl.integrations.litellm import check_key_lifecycle


def test_key_lifecycle_no_expiry():
    """key_expiry=None means indefinite — no violation."""
    result = check_key_lifecycle(
        key_alias="vk-test",
        key_expiry_iso=None,
        key_rotation_days=None,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    assert result["violation"] is False
    assert result["days_until_expiry"] is None
    assert result["rotation_overdue"] is False


def test_key_lifecycle_expired():
    """A key whose expiry is in the past must be flagged as a violation."""
    result = check_key_lifecycle(
        key_alias="vk-test",
        key_expiry_iso="2026-04-01T00:00:00Z",
        key_rotation_days=None,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    assert result["violation"] is True
    assert result["days_until_expiry"] < 0


def test_key_lifecycle_expiry_within_warning_window():
    """A key expiring in 10 days (< 14-day warning threshold) must be a violation."""
    expiry = datetime(2026, 5, 5, tzinfo=timezone.utc)
    result = check_key_lifecycle(
        key_alias="vk-test",
        key_expiry_iso=expiry.isoformat(),
        key_rotation_days=None,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    assert result["violation"] is True
    assert 0 < result["days_until_expiry"] <= 14


def test_key_lifecycle_rotation_overdue():
    """Key not rotated within key_rotation_days of its creation must be flagged."""
    result = check_key_lifecycle(
        key_alias="vk-test",
        key_expiry_iso="2027-01-01T00:00:00Z",
        key_rotation_days=30,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
        last_rotation_at_iso="2026-03-11T00:00:00Z",
    )
    assert result["rotation_overdue"] is True
    assert result["violation"] is True


def test_key_lifecycle_fresh_key_no_violation():
    """Key expiring in 30+ days with recent rotation — no violation."""
    result = check_key_lifecycle(
        key_alias="vk-test",
        key_expiry_iso="2026-07-01T00:00:00Z",
        key_rotation_days=30,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
        last_rotation_at_iso="2026-04-10T00:00:00Z",
    )
    assert result["violation"] is False
    assert result["rotation_overdue"] is False


@pytest.mark.asyncio
async def test_check_drift_detects_model_drift():
    """check_drift must flag when a live key allows models not in the approved contract."""
    client = _make_client()
    snapshot = {
        "litellm_agent_ids": [],
        "skill_content_hash": None,
        "mcp_allowlist": [],
        "agent_contracts": [
            {
                "agent_id": "agent-001",
                "key_alias": "vk-coord",
                "model_allowlist": ["claude-sonnet-4-6"],
            }
        ],
    }
    live_key = KeyDetails(
        key_alias="vk-coord",
        models=["claude-sonnet-4-6", "gpt-4o"],
        blocked=False,
        mcp_access_groups=[],
    )

    with patch.object(client, "get_key_details", new=AsyncMock(return_value=live_key)):
        report = await client.check_drift(snapshot)

    assert report.drifted is True
    assert any("gpt-4o" in v for v in report.violations)
    assert len(report.model_drift) == 1
    assert report.model_drift[0]["violation"] is True
    assert "gpt-4o" in report.model_drift[0]["unauthorized_models"]


@pytest.mark.asyncio
async def test_check_drift_detects_blocked_key():
    """check_drift must flag a blocked key as a liveness violation."""
    client = _make_client()
    snapshot = {
        "litellm_agent_ids": [],
        "skill_content_hash": None,
        "mcp_allowlist": [],
        "agent_contracts": [
            {"agent_id": "agent-001", "key_alias": "vk-blocked", "model_allowlist": []}
        ],
    }
    live_key = KeyDetails(key_alias="vk-blocked", models=[], blocked=True)

    with patch.object(client, "get_key_details", new=AsyncMock(return_value=live_key)):
        report = await client.check_drift(snapshot)

    assert report.drifted is True
    assert report.key_liveness is not None
    assert report.key_liveness["blocked"] is True


@pytest.mark.asyncio
async def test_check_drift_detects_mcp_permission_drift():
    """check_drift flags MCP access groups on live key not in snapshot mcp_allowlist."""
    client = _make_client()
    snapshot = {
        "litellm_agent_ids": [],
        "skill_content_hash": None,
        "mcp_allowlist": ["PeaRL-prod"],
        "agent_contracts": [
            {"agent_id": "agent-001", "key_alias": "vk-mcp", "model_allowlist": []}
        ],
    }
    live_key = KeyDetails(
        key_alias="vk-mcp",
        models=[],
        mcp_access_groups=["PeaRL-prod", "github-tools"],
        blocked=False,
    )

    with patch.object(client, "get_key_details", new=AsyncMock(return_value=live_key)):
        report = await client.check_drift(snapshot)

    assert report.drifted is True
    assert any("github-tools" in v for v in report.violations)


@pytest.mark.asyncio
async def test_check_drift_no_agent_contracts_fallback_to_agent_id_check():
    """Without agent_contracts, check_drift still checks agent IDs exist (old behavior)."""
    client = _make_client()
    snapshot = {
        "litellm_agent_ids": ["agent-legacy-001"],
        "skill_content_hash": None,
    }

    with patch.object(client, "get_agent", new=AsyncMock(return_value={"id": "agent-legacy-001"})):
        report = await client.check_drift(snapshot)

    assert report.drifted is False
    assert report.agents_checked == 1
