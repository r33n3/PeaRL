import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.db.models.agent_session import AgentSessionRow
from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
from pearl.repositories.agent_session_repo import AgentSessionRepository


# ── Task 3: BaseAgentPlatformAdapter ─────────────────────────────────────────

from pearl.integrations.adapters.base_agent import (
    AgentSessionResult,
    AgentSessionEvent,
    BaseAgentPlatformAdapter,
)


def test_agent_session_result_fields():
    r = AgentSessionResult(status="completed", output="done", files=[], cost_usd=0.01, raw={})
    assert r.status == "completed"
    assert r.output == "done"


def test_agent_session_event_fields():
    e = AgentSessionEvent(type="tool_call", content=None, tool_name="pearl_ingest_finding", raw={"id": "evt_1"})
    assert e.type == "tool_call"
    assert e.tool_name == "pearl_ingest_finding"


def test_base_adapter_is_abstract():
    assert inspect.isabstract(BaseAgentPlatformAdapter)


# ── Task 4: ClaudeManagedAgentsAdapter ───────────────────────────────────────

from pearl.integrations.adapters.claude_managed_agents import ClaudeManagedAgentsAdapter


@pytest.mark.asyncio
async def test_claude_adapter_create_session():
    adapter = ClaudeManagedAgentsAdapter(api_key="test-key")
    mock_session = MagicMock()
    mock_session.id = "sess_01abc"
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.sessions.create = AsyncMock(return_value=mock_session)
        session_id = await adapter.create_session(agent_id="agt_01xxx", task="Assess agent definition:\n\nname: test")
    assert session_id == "sess_01abc"


@pytest.mark.asyncio
async def test_claude_adapter_get_result_completed():
    adapter = ClaudeManagedAgentsAdapter(api_key="test-key")
    mock_session = MagicMock()
    mock_session.status = "completed"
    mock_session.output = [MagicMock(type="text", text=MagicMock(value="Assessment done."))]
    mock_session.usage = MagicMock(input_tokens=100, output_tokens=200)
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.sessions.retrieve = AsyncMock(return_value=mock_session)
        result = await adapter.get_result("sess_01abc")
    assert result.status == "completed"
    assert result.output == "Assessment done."
    assert result.cost_usd is not None


@pytest.mark.asyncio
async def test_claude_adapter_interrupt():
    adapter = ClaudeManagedAgentsAdapter(api_key="test-key")
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.sessions.interrupt = AsyncMock()
        await adapter.interrupt("sess_01abc")
    mock_client.beta.sessions.interrupt.assert_called_once_with("sess_01abc")


# ── Task 5: OpenAIAgentsAdapter ──────────────────────────────────────────────

from pearl.integrations.adapters.openai_agents import OpenAIAgentsAdapter


@pytest.mark.asyncio
async def test_openai_adapter_create_session():
    adapter = OpenAIAgentsAdapter(api_key="test-key")
    mock_thread = MagicMock()
    mock_thread.id = "thread_abc"
    mock_run = MagicMock()
    mock_run.id = "run_001"
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.threads.create = AsyncMock(return_value=mock_thread)
        mock_client.beta.threads.runs.create = AsyncMock(return_value=mock_run)
        session_id = await adapter.create_session(agent_id="wf_123", task="Assess agent definition:\n\nname: test")
    assert session_id == "thread_abc:run_001"


@pytest.mark.asyncio
async def test_openai_adapter_get_result_completed():
    adapter = OpenAIAgentsAdapter(api_key="test-key")
    mock_run = MagicMock()
    mock_run.status = "completed"
    mock_run.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    mock_messages = MagicMock()
    msg = MagicMock()
    msg.role = "assistant"
    msg.content = [MagicMock(type="text", text=MagicMock(value="Assessment complete."))]
    mock_messages.data = [msg]
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.threads.runs.retrieve = AsyncMock(return_value=mock_run)
        mock_client.beta.threads.messages.list = AsyncMock(return_value=mock_messages)
        result = await adapter.get_result("thread_abc:run_001")
    assert result.status == "completed"
    assert result.output == "Assessment complete."


@pytest.mark.asyncio
async def test_openai_adapter_interrupt():
    adapter = OpenAIAgentsAdapter(api_key="test-key")
    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.threads.runs.cancel = AsyncMock(return_value=MagicMock())
        await adapter.interrupt("thread_abc:run_001")
    mock_client.beta.threads.runs.cancel.assert_called_once_with(thread_id="thread_abc", run_id="run_001")


def test_agent_definition_row_has_expected_columns():
    cols = {c.key for c in AgentDefinitionRow.__table__.columns}
    assert {"agent_definition_id", "project_id", "git_ref", "git_path",
            "platform", "platform_agent_id", "definition", "capabilities",
            "environment", "status", "version", "created_at"} <= cols


def test_agent_session_row_has_expected_columns():
    cols = {c.key for c in AgentSessionRow.__table__.columns}
    assert {"agent_session_id", "definition_id", "project_id", "platform",
            "platform_session_id", "purpose", "status", "result",
            "cost_usd", "started_at", "completed_at"} <= cols


def test_agent_definition_status_default():
    # default value is set on the ORM object
    row = AgentDefinitionRow.__new__(AgentDefinitionRow)
    assert AgentDefinitionRow.status.property.columns[0].default.arg == "pending_assessment"


@pytest.mark.asyncio
async def test_agent_definition_create_and_get(db_session):
    repo = AgentDefinitionRepository(db_session)
    row = await repo.create(
        project_id="proj_test",
        git_ref="abc123",
        git_path="agents/orchestrator/agent.yaml",
        platform="claude",
        platform_agent_id="agt_01xxx",
        definition={"name": "test-agent"},
        capabilities={"tools": ["bash"]},
        environment="dev",
        version="abc123",
    )
    assert row.agent_definition_id.startswith("def_")
    assert row.status == "pending_assessment"

    fetched = await repo.get(row.agent_definition_id)
    assert fetched is not None
    assert fetched.project_id == "proj_test"


@pytest.mark.asyncio
async def test_agent_definition_update_status(db_session):
    repo = AgentDefinitionRepository(db_session)
    row = await repo.create(
        project_id="proj_test",
        git_ref="abc456",
        git_path="agents/agent.yaml",
        platform="openai",
        platform_agent_id=None,
        definition={"name": "openai-agent"},
        capabilities={},
        environment="dev",
        version="abc456",
    )
    updated = await repo.update_status(row.agent_definition_id, "assessed")
    assert updated.status == "assessed"


@pytest.mark.asyncio
async def test_agent_definition_get_latest_for_project(db_session):
    repo = AgentDefinitionRepository(db_session)
    await repo.create(
        project_id="proj_env_test",
        git_ref="sha001",
        git_path="agents/agent.yaml",
        platform="claude",
        platform_agent_id=None,
        definition={},
        capabilities={},
        environment="dev",
        version="sha001",
    )
    result = await repo.get_latest_for_project("proj_env_test", environment="dev")
    assert result is not None
    assert result.environment == "dev"


@pytest.mark.asyncio
async def test_agent_session_create_and_get(db_session):
    repo = AgentSessionRepository(db_session)
    row = await repo.create(
        definition_id="def_abc",
        project_id="proj_test",
        platform="claude",
        platform_session_id="sess_01xxx",
        purpose="assessment",
    )
    assert row.agent_session_id.startswith("ses_")
    assert row.status == "running"

    fetched = await repo.get(row.agent_session_id)
    assert fetched is not None
    assert fetched.platform_session_id == "sess_01xxx"


@pytest.mark.asyncio
async def test_agent_session_update_result(db_session):
    repo = AgentSessionRepository(db_session)
    row = await repo.create(
        definition_id="def_xyz",
        project_id="proj_test",
        platform="openai",
        platform_session_id="run_001",
        purpose="assessment",
    )
    updated = await repo.update_result(
        row.agent_session_id,
        status="completed",
        result={"verdict": "pass", "findings_count": 0},
        cost_usd=0.05,
    )
    assert updated.status == "completed"
    assert updated.result["findings_count"] == 0
    assert updated.completed_at is not None


# ── Task 6: get_agent_platform_adapter factory + config settings ──────────────

from pearl.integrations.adapters import get_agent_platform_adapter


def test_get_agent_platform_adapter_claude():
    adapter = get_agent_platform_adapter("claude", api_key="test-key")
    assert isinstance(adapter, ClaudeManagedAgentsAdapter)


def test_get_agent_platform_adapter_openai():
    adapter = get_agent_platform_adapter("openai", api_key="test-key")
    assert isinstance(adapter, OpenAIAgentsAdapter)


def test_get_agent_platform_adapter_unknown():
    with pytest.raises(ValueError, match="Unknown platform"):
        get_agent_platform_adapter("unknown", api_key="test-key")


from pearl.config import Settings


def test_settings_has_agent_platform_fields():
    s = Settings(
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
        mass_platform="openai",
        mass_agent_id="wf_001",
        mass_environment_id="env_abc",
    )
    assert s.mass_platform == "openai"
    assert s.mass_agent_id == "wf_001"
    assert s.anthropic_api_key == "sk-ant-test"


# ── Task 7: AgentAssessmentService ───────────────────────────────────────────

from pearl.services.agent_assessment import AgentAssessmentService
from sqlalchemy import select


@pytest.mark.asyncio
async def test_assess_definition_creates_session_and_row(db_session):
    mock_adapter = MagicMock(spec=BaseAgentPlatformAdapter)
    mock_adapter.create_session = AsyncMock(return_value="sess_test_001")

    service = AgentAssessmentService(adapter=mock_adapter, session=db_session)

    platform_session_id = await service.assess_definition(
        project_id="proj_test",
        definition_id="def_abc",
        platform="claude",
        definition_yaml="name: test-agent\ntools: [bash]",
    )

    assert platform_session_id == "sess_test_001"
    mock_adapter.create_session.assert_called_once()

    result = await db_session.execute(
        select(AgentSessionRow).where(AgentSessionRow.platform_session_id == "sess_test_001")
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.purpose == "assessment"
    assert row.status == "running"


@pytest.mark.asyncio
async def test_assess_definition_uses_mass_agent_id(db_session):
    mock_adapter = MagicMock(spec=BaseAgentPlatformAdapter)
    mock_adapter.create_session = AsyncMock(return_value="sess_test_002")

    service = AgentAssessmentService(
        adapter=mock_adapter,
        session=db_session,
        mass_agent_id="agt_01testxxx",
    )
    await service.assess_definition(
        project_id="proj_test",
        definition_id="def_xyz",
        platform="claude",
        definition_yaml="name: second-agent",
    )

    call_args = mock_adapter.create_session.call_args
    # agent_id should be the mass_agent_id — either positional or keyword
    all_args = list(call_args.args) + list(call_args.kwargs.values())
    assert "agt_01testxxx" in all_args


# ── Task 8: POST /agent-definitions endpoint ──────────────────────────────────


@pytest.mark.asyncio
async def test_post_agent_definition_creates_row(client):
    payload = {
        "git_ref": "abc123def",
        "git_path": "agents/orchestrator/agent.yaml",
        "platform": "claude",
        "platform_agent_id": "agt_01xxx",
        "definition": "name: test-orchestrator\ntools:\n  - bash\n",
        "environment": "dev",
    }
    resp = await client.post("/api/v1/projects/proj_myapp001/agent-definitions", json=payload)
    assert resp.status_code == 202
    body = resp.json()
    assert body["definition_id"].startswith("def_")
    assert body["status"] == "pending_assessment"


@pytest.mark.asyncio
async def test_post_agent_definition_missing_required_fields(client):
    resp = await client.post(
        "/api/v1/projects/proj_myapp001/agent-definitions",
        json={"git_ref": "abc123"},
    )
    assert resp.status_code == 422


# ── Task 9: Gate rule agent_definition_assessed ───────────────────────────────

from pearl.services.promotion.gate_evaluator import _EvalContext


def test_eval_context_has_agent_definition_fields():
    ctx = _EvalContext()
    assert hasattr(ctx, "agent_definition_id")
    assert hasattr(ctx, "agent_definition_status")
    assert ctx.agent_definition_id is None
    assert ctx.agent_definition_status is None


def test_agent_definition_assessed_rule_approved():
    from pearl.services.promotion.gate_evaluator import _eval_agent_definition_assessed
    ctx = _EvalContext()
    ctx.agent_definition_id = "def_abc"
    ctx.agent_definition_status = "approved"
    passed, reason, _ = _eval_agent_definition_assessed({}, ctx)
    assert passed is True
    assert "approved" in reason


def test_agent_definition_assessed_rule_rejected():
    from pearl.services.promotion.gate_evaluator import _eval_agent_definition_assessed
    ctx = _EvalContext()
    ctx.agent_definition_id = "def_abc"
    ctx.agent_definition_status = "rejected"
    passed, reason, _ = _eval_agent_definition_assessed({}, ctx)
    assert passed is False
    assert "rejected" in reason.lower()


def test_agent_definition_assessed_rule_pending():
    from pearl.services.promotion.gate_evaluator import _eval_agent_definition_assessed
    ctx = _EvalContext()
    ctx.agent_definition_id = "def_abc"
    ctx.agent_definition_status = "pending_assessment"
    passed, reason, _ = _eval_agent_definition_assessed({}, ctx)
    assert passed is False
    assert "pending" in reason.lower()


def test_agent_definition_assessed_rule_no_definition():
    from pearl.services.promotion.gate_evaluator import _eval_agent_definition_assessed
    ctx = _EvalContext()
    ctx.agent_definition_id = None
    passed, reason, _ = _eval_agent_definition_assessed({}, ctx)
    assert passed is True
    assert "non-agent" in reason.lower() or "no agent" in reason.lower()
