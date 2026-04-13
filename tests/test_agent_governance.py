from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.db.models.agent_session import AgentSessionRow


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
