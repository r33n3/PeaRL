"""Contract compliance client tests."""

import pytest
from unittest.mock import AsyncMock, patch

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

    mock_response_info = AsyncMock()
    mock_response_info.status_code = 200
    mock_response_info.json = lambda: key_info

    mock_response_logs = AsyncMock()
    mock_response_logs.status_code = 200
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

    mock_info = AsyncMock()
    mock_info.status_code = 200
    mock_info.json = lambda: key_info
    mock_logs = AsyncMock()
    mock_logs.status_code = 200
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

    mock_info = AsyncMock()
    mock_info.status_code = 200
    mock_info.json = lambda: key_info
    mock_logs = AsyncMock()
    mock_logs.status_code = 200
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
