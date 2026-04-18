"""Contract compliance client tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient as HttpxClient

import httpx

from pearl.integrations.litellm import LiteLLMClient, ContractCompliance


@pytest.fixture
def client():
    return LiteLLMClient(base_url="http://litellm:4000", api_key="sk-builder-key")


@pytest.mark.asyncio
async def test_get_key_compliance_passed(client):
    """Compliance passes when spend is within budget and only allowed models used."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 10.0,
        "spend": 2.5,
        "metadata": {"run_id": "abc", "task_packet_id": "tp_123"},
    }
    spend_logs = [
        {"model": "ollama-qwen3.5", "spend": 1.5},
        {"model": "ollama-qwen3.5", "spend": 1.0},
    ]

    mock_response_info = MagicMock()
    mock_response_info.status_code = 200
    mock_response_info.raise_for_status = lambda: None
    mock_response_info.json = lambda: key_info

    mock_response_logs = MagicMock()
    mock_response_logs.status_code = 200
    mock_response_logs.raise_for_status = lambda: None
    mock_response_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_response_info, mock_response_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert isinstance(result, ContractCompliance)
    assert result.passed is True
    assert result.violations == []
    assert result.actual_spend_usd == pytest.approx(2.5)
    assert result.actual_models_used == ["ollama-qwen3.5"]


@pytest.mark.asyncio
async def test_get_key_compliance_budget_exceeded(client):
    """Compliance fails when actual spend exceeds budget_cap_usd."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 5.0,
        "spend": 7.3,
        "metadata": {},
    }
    spend_logs = [{"model": "ollama-qwen3.5", "spend": 7.3}]

    mock_info = MagicMock()
    mock_info.status_code = 200
    mock_info.raise_for_status = lambda: None
    mock_info.json = lambda: key_info
    mock_logs = MagicMock()
    mock_logs.status_code = 200
    mock_logs.raise_for_status = lambda: None
    mock_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_info, mock_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=5.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is False
    assert any("budget" in v.lower() for v in result.violations)


@pytest.mark.asyncio
async def test_get_key_compliance_unauthorized_model(client):
    """Compliance fails when agent called a model outside allowed_models."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 10.0,
        "spend": 1.0,
        "metadata": {},
    }
    spend_logs = [
        {"model": "ollama-qwen3.5", "spend": 0.5},
        {"model": "gpt-4o", "spend": 0.5},
    ]

    mock_info = MagicMock()
    mock_info.status_code = 200
    mock_info.raise_for_status = lambda: None
    mock_info.json = lambda: key_info
    mock_logs = MagicMock()
    mock_logs.status_code = 200
    mock_logs.raise_for_status = lambda: None
    mock_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_info, mock_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is False
    assert any("gpt-4o" in v for v in result.violations)


@pytest.mark.asyncio
async def test_get_key_compliance_litellm_unreachable(client):
    """Returns passed=True with unreachable note when LiteLLM is down (graceful degradation)."""
    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is True
    assert len(result.violations) == 1
    assert "unreachable" in result.violations[0].lower()


@pytest.mark.asyncio
async def test_get_key_compliance_litellm_non_200(client):
    """Non-200 from LiteLLM degrades gracefully rather than silently passing with zero spend."""
    mock_info = MagicMock()
    mock_info.status_code = 401

    def _raise():
        raise httpx.HTTPStatusError("401", request=MagicMock(), response=mock_info)

    mock_info.raise_for_status = _raise

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_info)

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is True
    assert len(result.violations) == 1
    assert "unreachable" in result.violations[0].lower()


# ─── Route integration tests ──────────────────────────────────────────────────

async def _seed_task_packet(db_session, task_packet_id: str, packet_data: dict, allowance_profile_id: str | None = None):
    """Directly seed a TaskPacketRow for testing."""
    from pearl.db.models.task_packet import TaskPacketRow

    row = TaskPacketRow(
        task_packet_id=task_packet_id,
        project_id="proj_compliance_test",
        environment="dev",
        trace_id="trace_test",
        schema_version=1,
        packet_data=packet_data,
        allowance_profile_id=allowance_profile_id,
    )
    db_session.add(row)
    await db_session.commit()


@pytest.mark.asyncio
async def test_contract_compliance_route_no_litellm_config(app, db_session):
    """Returns 503 when PEARL_LITELLM_API_URL is not configured."""
    await _seed_task_packet(
        db_session,
        task_packet_id="tp_compliance503",
        packet_data={"run_id": "run_abc123", "goal": "test"},
    )

    async with HttpxClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("pearl.api.routes.task_packets.settings") as mock_settings:
            mock_settings.litellm_api_url = ""
            mock_settings.litellm_api_key = "sk-key"
            r = await ac.get("/api/v1/task-packets/tp_compliance503/contract-compliance")

    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contract_compliance_route_no_run_id(app, db_session):
    """Returns 200 with skip note when packet_data has no run_id."""
    await _seed_task_packet(
        db_session,
        task_packet_id="tp_complianceskip",
        packet_data={"goal": "test"},
    )

    async with HttpxClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("pearl.api.routes.task_packets.settings") as mock_settings:
            mock_settings.litellm_api_url = "http://litellm:4000"
            mock_settings.litellm_api_key = "sk-builder"
            r = await ac.get("/api/v1/task-packets/tp_complianceskip/contract-compliance")

    assert r.status_code == 200
    body = r.json()
    assert body["passed"] is True
    assert any("run_id" in v.lower() for v in body["violations"])
