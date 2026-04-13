import pytest
from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.db.models.agent_session import AgentSessionRow
from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
from pearl.repositories.agent_session_repo import AgentSessionRepository


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
