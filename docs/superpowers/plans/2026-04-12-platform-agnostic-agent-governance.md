# Platform-Agnostic Agent Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor PeaRL to govern Claude Managed Agents and OpenAI Agents API deployments, replacing the self-hosted MASS Docker stack with a config-driven managed agent platform adapter.

**Architecture:** PeaRL receives agent YAML/JSON definitions via `POST /agent-definitions`, creates a platform session (Claude or OpenAI) via `AgentAssessmentService`, and MASS runs as a Managed Agent that pushes findings through PeaRL's existing MCP tools. Platform selection is `MASS_PLATFORM` config — no code changes to switch.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Anthropic SDK (`anthropic.beta.sessions`), OpenAI SDK (threads + runs), pytest-asyncio

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `src/pearl/db/models/agent_definition.py` | `AgentDefinitionRow` ORM model |
| `src/pearl/db/models/agent_session.py` | `AgentSessionRow` ORM model |
| `src/pearl/db/migrations/versions/007_add_agent_definitions.py` | Alembic migration for `agent_definitions` |
| `src/pearl/db/migrations/versions/008_add_agent_sessions.py` | Alembic migration for `agent_sessions` |
| `src/pearl/repositories/agent_definition_repo.py` | CRUD for `agent_definitions` |
| `src/pearl/repositories/agent_session_repo.py` | CRUD for `agent_sessions` |
| `src/pearl/integrations/adapters/base_agent.py` | `BaseAgentPlatformAdapter` ABC + `AgentSessionResult` + `AgentSessionEvent` |
| `src/pearl/integrations/adapters/claude_managed_agents.py` | `ClaudeManagedAgentsAdapter` |
| `src/pearl/integrations/adapters/openai_agents.py` | `OpenAIAgentsAdapter` |
| `src/pearl/services/agent_assessment.py` | `AgentAssessmentService` |
| `src/pearl/api/routes/agent_definitions.py` | `POST /projects/{project_id}/agent-definitions` |
| `tests/test_agent_governance.py` | All tests for Tasks 1–8 |

### Modified files
| File | Change |
|---|---|
| `src/pearl/db/models/__init__.py` | Import `AgentDefinitionRow`, `AgentSessionRow` |
| `src/pearl/config.py` | Add `anthropic_api_key`, `openai_api_key`, `mass_platform`, `mass_agent_id`, `mass_environment_id` |
| `src/pearl/api/router.py` | Register `agent_definitions` router |
| `src/pearl/integrations/adapters/__init__.py` | Add `get_agent_platform_adapter()` factory |
| `src/pearl/services/promotion/gate_evaluator.py` | Add `agent_definition_id`, `agent_definition_status` to `_EvalContext`; add `agent_definition_assessed` rule; load from DB in `_build_eval_context` |

### Deleted (Task 9, after platform migration confirmed)
- `src/pearl/scanning/mass_bridge.py`

---

## Task 1: Agent Data Models

**Files:**
- Create: `src/pearl/db/models/agent_definition.py`
- Create: `src/pearl/db/models/agent_session.py`
- Create: `src/pearl/db/migrations/versions/007_add_agent_definitions.py`
- Create: `src/pearl/db/migrations/versions/008_add_agent_sessions.py`
- Modify: `src/pearl/db/models/__init__.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests for models**

```python
# tests/test_agent_governance.py
import pytest
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


def test_agent_definition_status_values():
    # valid status values documented in spec
    valid = {"pending_assessment", "assessed", "approved", "rejected"}
    assert valid  # column exists, values checked at app layer
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py -v
```
Expected: `ImportError` — modules don't exist yet.

- [ ] **Step 3: Create `AgentDefinitionRow`**

```python
# src/pearl/db/models/agent_definition.py
"""AgentDefinitionRow — tracks agent YAML/JSON definitions submitted for assessment."""

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base


class AgentDefinitionRow(Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("project_id", "git_ref", "git_path", "environment",
                         name="uq_agent_definition"),
    )

    agent_definition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    git_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    git_path: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)   # "claude" | "openai"
    platform_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)  # "dev" | "prod"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_assessment")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Create `AgentSessionRow`**

```python
# src/pearl/db/models/agent_session.py
"""AgentSessionRow — tracks sessions created on agent platforms (Claude/OpenAI)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base


class AgentSessionRow(Base):
    __tablename__ = "agent_sessions"

    agent_session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)   # "claude" | "openai"
    platform_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)    # "assessment" | "execution" | "remediation"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Create migration 007**

```python
# src/pearl/db/migrations/versions/007_add_agent_definitions.py
"""Add agent_definitions table.

Revision ID: 007
Revises: 006
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("agent_definitions"):
        return
    op.create_table(
        "agent_definitions",
        sa.Column("agent_definition_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), nullable=False, index=True),
        sa.Column("git_ref", sa.String(64), nullable=False),
        sa.Column("git_path", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_agent_id", sa.String(128), nullable=True),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_assessment"),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "git_ref", "git_path", "environment",
                            name="uq_agent_definition"),
    )


def downgrade() -> None:
    op.drop_table("agent_definitions")
```

- [ ] **Step 6: Create migration 008**

```python
# src/pearl/db/migrations/versions/008_add_agent_sessions.py
"""Add agent_sessions table.

Revision ID: 008
Revises: 007
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("agent_sessions"):
        return
    op.create_table(
        "agent_sessions",
        sa.Column("agent_session_id", sa.String(64), primary_key=True),
        sa.Column("definition_id", sa.String(64), nullable=False, index=True),
        sa.Column("project_id", sa.String(128), nullable=False, index=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_session_id", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_sessions")
```

- [ ] **Step 7: Register models in `__init__.py`**

Add at end of `src/pearl/db/models/__init__.py`:
```python
from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.db.models.agent_session import AgentSessionRow
```

- [ ] **Step 8: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py -v
```
Expected: all 3 pass.

- [ ] **Step 9: Commit**

```bash
git add src/pearl/db/models/agent_definition.py \
        src/pearl/db/models/agent_session.py \
        src/pearl/db/migrations/versions/007_add_agent_definitions.py \
        src/pearl/db/migrations/versions/008_add_agent_sessions.py \
        src/pearl/db/models/__init__.py \
        tests/test_agent_governance.py
git commit -m "feat: add AgentDefinitionRow and AgentSessionRow models + migrations 007/008"
```

---

## Task 2: Repositories

**Files:**
- Create: `src/pearl/repositories/agent_definition_repo.py`
- Create: `src/pearl/repositories/agent_session_repo.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests for repositories**

Add to `tests/test_agent_governance.py`:
```python
from datetime import datetime, timezone
import pytest
from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
from pearl.repositories.agent_session_repo import AgentSessionRepository


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
async def test_agent_definition_get_current_for_project(db_session):
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
async def test_agent_session_update_status(db_session):
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py -v
```
Expected: `ImportError` — repositories don't exist yet.

- [ ] **Step 3: Create `AgentDefinitionRepository`**

```python
# src/pearl/repositories/agent_definition_repo.py
"""Repository for agent_definitions table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.services.id_generator import generate_id


class AgentDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        project_id: str,
        git_ref: str,
        git_path: str,
        platform: str,
        platform_agent_id: str | None,
        definition: dict,
        capabilities: dict,
        environment: str,
        version: str,
    ) -> AgentDefinitionRow:
        row = AgentDefinitionRow(
            agent_definition_id=generate_id("def"),
            project_id=project_id,
            git_ref=git_ref,
            git_path=git_path,
            platform=platform,
            platform_agent_id=platform_agent_id,
            definition=definition,
            capabilities=capabilities,
            environment=environment,
            status="pending_assessment",
            version=version,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, definition_id: str) -> AgentDefinitionRow | None:
        result = await self._session.execute(
            select(AgentDefinitionRow).where(
                AgentDefinitionRow.agent_definition_id == definition_id
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_for_project(
        self, project_id: str, environment: str
    ) -> AgentDefinitionRow | None:
        result = await self._session.execute(
            select(AgentDefinitionRow)
            .where(
                AgentDefinitionRow.project_id == project_id,
                AgentDefinitionRow.environment == environment,
            )
            .order_by(AgentDefinitionRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, definition_id: str, status: str
    ) -> AgentDefinitionRow:
        row = await self.get(definition_id)
        if row is None:
            raise ValueError(f"AgentDefinitionRow not found: {definition_id}")
        row.status = status
        await self._session.flush()
        return row
```

- [ ] **Step 4: Create `AgentSessionRepository`**

```python
# src/pearl/repositories/agent_session_repo.py
"""Repository for agent_sessions table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.agent_session import AgentSessionRow
from pearl.services.id_generator import generate_id


class AgentSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        definition_id: str,
        project_id: str,
        platform: str,
        platform_session_id: str,
        purpose: str,
    ) -> AgentSessionRow:
        row = AgentSessionRow(
            agent_session_id=generate_id("ses"),
            definition_id=definition_id,
            project_id=project_id,
            platform=platform,
            platform_session_id=platform_session_id,
            purpose=purpose,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, session_id: str) -> AgentSessionRow | None:
        result = await self._session.execute(
            select(AgentSessionRow).where(
                AgentSessionRow.agent_session_id == session_id
            )
        )
        return result.scalar_one_or_none()

    async def update_result(
        self,
        session_id: str,
        status: str,
        result: dict | None = None,
        cost_usd: float | None = None,
    ) -> AgentSessionRow:
        row = await self.get(session_id)
        if row is None:
            raise ValueError(f"AgentSessionRow not found: {session_id}")
        row.status = status
        if result is not None:
            row.result = result
        if cost_usd is not None:
            row.cost_usd = cost_usd
        if status in ("completed", "failed", "interrupted"):
            row.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py -v
```
Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/pearl/repositories/agent_definition_repo.py \
        src/pearl/repositories/agent_session_repo.py \
        tests/test_agent_governance.py
git commit -m "feat: add AgentDefinitionRepository and AgentSessionRepository"
```

---

## Task 3: Adapter Interface and Common Types

**Files:**
- Create: `src/pearl/integrations/adapters/base_agent.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
from pearl.integrations.adapters.base_agent import (
    AgentSessionResult,
    AgentSessionEvent,
    BaseAgentPlatformAdapter,
)


def test_agent_session_result_fields():
    r = AgentSessionResult(
        status="completed",
        output="done",
        files=[],
        cost_usd=0.01,
        raw={},
    )
    assert r.status == "completed"
    assert r.output == "done"


def test_agent_session_event_fields():
    e = AgentSessionEvent(
        type="tool_call",
        content=None,
        tool_name="pearl_ingest_finding",
        raw={"id": "evt_1"},
    )
    assert e.type == "tool_call"
    assert e.tool_name == "pearl_ingest_finding"


def test_base_adapter_is_abstract():
    import inspect
    assert inspect.isabstract(BaseAgentPlatformAdapter)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_agent_session_result_fields \
    tests/test_agent_governance.py::test_agent_session_event_fields \
    tests/test_agent_governance.py::test_base_adapter_is_abstract -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `base_agent.py`**

```python
# src/pearl/integrations/adapters/base_agent.py
"""Abstract base adapter for agent platforms (Claude Managed Agents, OpenAI Agents API)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class AgentSessionResult:
    status: str           # "completed" | "failed" | "interrupted"
    output: str | None    # final text output from the session
    files: list[str]      # file IDs (Claude Files API) or attachment IDs
    cost_usd: float | None
    raw: dict             # full platform response for debugging


@dataclass
class AgentSessionEvent:
    type: str             # "message" | "tool_call" | "tool_result" | "status_change"
    content: str | None
    tool_name: str | None
    raw: dict


class BaseAgentPlatformAdapter(ABC):
    """Common interface for all agent platform adapters."""

    @abstractmethod
    async def create_session(
        self,
        agent_id: str,
        task: str,
        environment_id: str | None = None,
    ) -> str:
        """Create a session on the platform. Returns platform_session_id."""
        ...

    @abstractmethod
    async def get_result(self, session_id: str) -> AgentSessionResult:
        """Retrieve the final result of a completed session."""
        ...

    @abstractmethod
    async def stream_events(
        self, session_id: str
    ) -> AsyncIterator[AgentSessionEvent]:
        """Stream events from a running session."""
        ...

    @abstractmethod
    async def interrupt(self, session_id: str) -> None:
        """Request interruption of a running session."""
        ...
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_agent_session_result_fields \
    tests/test_agent_governance.py::test_agent_session_event_fields \
    tests/test_agent_governance.py::test_base_adapter_is_abstract -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/integrations/adapters/base_agent.py tests/test_agent_governance.py
git commit -m "feat: add BaseAgentPlatformAdapter interface with AgentSessionResult/Event types"
```

---

## Task 4: ClaudeManagedAgentsAdapter

**Files:**
- Create: `src/pearl/integrations/adapters/claude_managed_agents.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch
from pearl.integrations.adapters.claude_managed_agents import ClaudeManagedAgentsAdapter


@pytest.mark.asyncio
async def test_claude_adapter_create_session():
    """create_session calls anthropic beta sessions and returns session_id."""
    adapter = ClaudeManagedAgentsAdapter(api_key="test-key")

    mock_session = MagicMock()
    mock_session.id = "sess_01abc"

    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.sessions.create = AsyncMock(return_value=mock_session)
        session_id = await adapter.create_session(
            agent_id="agt_01xxx",
            task="Assess agent definition:\n\nname: test",
        )
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_claude_adapter_create_session \
    tests/test_agent_governance.py::test_claude_adapter_get_result_completed \
    tests/test_agent_governance.py::test_claude_adapter_interrupt -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `claude_managed_agents.py`**

```python
# src/pearl/integrations/adapters/claude_managed_agents.py
"""Adapter for Anthropic Claude Managed Agents platform."""
from __future__ import annotations

import logging
from typing import AsyncIterator

import anthropic

from pearl.integrations.adapters.base_agent import (
    AgentSessionEvent,
    AgentSessionResult,
    BaseAgentPlatformAdapter,
)

logger = logging.getLogger(__name__)

# Claude pricing (input/output per 1M tokens) — Sonnet 3.5 as reference
_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000


class ClaudeManagedAgentsAdapter(BaseAgentPlatformAdapter):
    """Wraps Anthropic beta sessions API for Claude Managed Agents."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def create_session(
        self,
        agent_id: str,
        task: str,
        environment_id: str | None = None,
    ) -> str:
        kwargs: dict = {"agent": agent_id, "input": task}
        if environment_id:
            kwargs["environment"] = environment_id
        session = await self._client.beta.sessions.create(**kwargs)
        logger.info("claude_session_created agent_id=%s session_id=%s", agent_id, session.id)
        return session.id

    async def get_result(self, session_id: str) -> AgentSessionResult:
        session = await self._client.beta.sessions.retrieve(session_id)

        output_text: str | None = None
        files: list[str] = []
        for block in getattr(session, "output", []) or []:
            if getattr(block, "type", None) == "text":
                output_text = block.text.value
            elif getattr(block, "type", None) == "file":
                files.append(block.file.file_id)

        cost_usd: float | None = None
        usage = getattr(session, "usage", None)
        if usage:
            cost_usd = (
                getattr(usage, "input_tokens", 0) * _COST_PER_INPUT_TOKEN
                + getattr(usage, "output_tokens", 0) * _COST_PER_OUTPUT_TOKEN
            )

        return AgentSessionResult(
            status=session.status,
            output=output_text,
            files=files,
            cost_usd=cost_usd,
            raw=session.model_dump() if hasattr(session, "model_dump") else {},
        )

    async def stream_events(self, session_id: str) -> AsyncIterator[AgentSessionEvent]:
        async with self._client.beta.sessions.threads.stream(session_id) as stream:
            async for event in stream:
                event_type = getattr(event, "type", "unknown")
                content: str | None = None
                tool_name: str | None = None

                if event_type in ("content_block_delta", "message_delta"):
                    delta = getattr(event, "delta", None)
                    if delta:
                        content = getattr(delta, "text", None) or getattr(delta, "value", None)
                elif event_type == "tool_use":
                    tool_name = getattr(event, "name", None)
                    content = str(getattr(event, "input", ""))

                yield AgentSessionEvent(
                    type=event_type,
                    content=content,
                    tool_name=tool_name,
                    raw=event.model_dump() if hasattr(event, "model_dump") else {},
                )

    async def interrupt(self, session_id: str) -> None:
        await self._client.beta.sessions.interrupt(session_id)
        logger.info("claude_session_interrupted session_id=%s", session_id)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_claude_adapter_create_session \
    tests/test_agent_governance.py::test_claude_adapter_get_result_completed \
    tests/test_agent_governance.py::test_claude_adapter_interrupt -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/integrations/adapters/claude_managed_agents.py tests/test_agent_governance.py
git commit -m "feat: add ClaudeManagedAgentsAdapter"
```

---

## Task 5: OpenAIAgentsAdapter

**Files:**
- Create: `src/pearl/integrations/adapters/openai_agents.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch
from pearl.integrations.adapters.openai_agents import OpenAIAgentsAdapter


@pytest.mark.asyncio
async def test_openai_adapter_create_session():
    """create_session creates thread + run and returns run_id."""
    adapter = OpenAIAgentsAdapter(api_key="test-key")

    mock_thread = MagicMock()
    mock_thread.id = "thread_abc"
    mock_run = MagicMock()
    mock_run.id = "run_001"

    with patch.object(adapter, "_client") as mock_client:
        mock_client.beta.threads.create = AsyncMock(return_value=mock_thread)
        mock_client.beta.threads.runs.create = AsyncMock(return_value=mock_run)
        session_id = await adapter.create_session(
            agent_id="wf_123",
            task="Assess agent definition:\n\nname: test",
        )

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
    mock_client.beta.threads.runs.cancel.assert_called_once_with(
        thread_id="thread_abc", run_id="run_001"
    )
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_openai_adapter_create_session \
    tests/test_agent_governance.py::test_openai_adapter_get_result_completed \
    tests/test_agent_governance.py::test_openai_adapter_interrupt -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `openai_agents.py`**

```python
# src/pearl/integrations/adapters/openai_agents.py
"""Adapter for OpenAI Agents API (threads/runs against workflow ID)."""
from __future__ import annotations

import logging
from typing import AsyncIterator

import openai

from pearl.integrations.adapters.base_agent import (
    AgentSessionEvent,
    AgentSessionResult,
    BaseAgentPlatformAdapter,
)

logger = logging.getLogger(__name__)

_COST_PER_INPUT_TOKEN = 2.5 / 1_000_000   # GPT-4o reference pricing
_COST_PER_OUTPUT_TOKEN = 10.0 / 1_000_000


class OpenAIAgentsAdapter(BaseAgentPlatformAdapter):
    """Wraps OpenAI Assistants/Agents API (beta threads + runs)."""

    def __init__(self, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def create_session(
        self,
        agent_id: str,
        task: str,
        environment_id: str | None = None,
    ) -> str:
        """Creates a thread with the task as user message, then starts a run.

        Returns composite session_id: "<thread_id>:<run_id>"
        """
        thread = await self._client.beta.threads.create(
            messages=[{"role": "user", "content": task}]
        )
        run = await self._client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=agent_id,
        )
        composite_id = f"{thread.id}:{run.id}"
        logger.info("openai_run_created agent_id=%s composite_id=%s", agent_id, composite_id)
        return composite_id

    def _parse_id(self, session_id: str) -> tuple[str, str]:
        thread_id, run_id = session_id.split(":", 1)
        return thread_id, run_id

    async def get_result(self, session_id: str) -> AgentSessionResult:
        thread_id, run_id = self._parse_id(session_id)
        run = await self._client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run_id
        )

        output_text: str | None = None
        messages = await self._client.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for block in msg.content:
                    if getattr(block, "type", None) == "text":
                        output_text = block.text.value
                break

        cost_usd: float | None = None
        usage = getattr(run, "usage", None)
        if usage:
            cost_usd = (
                getattr(usage, "prompt_tokens", 0) * _COST_PER_INPUT_TOKEN
                + getattr(usage, "completion_tokens", 0) * _COST_PER_OUTPUT_TOKEN
            )

        status_map = {
            "completed": "completed",
            "failed": "failed",
            "cancelled": "interrupted",
            "expired": "failed",
        }
        status = status_map.get(run.status, run.status)

        return AgentSessionResult(
            status=status,
            output=output_text,
            files=[],
            cost_usd=cost_usd,
            raw=run.model_dump() if hasattr(run, "model_dump") else {},
        )

    async def stream_events(self, session_id: str) -> AsyncIterator[AgentSessionEvent]:
        thread_id, run_id = self._parse_id(session_id)
        async with self._client.beta.threads.runs.stream(
            thread_id=thread_id, run_id=run_id
        ) as stream:
            async for event in stream:
                event_type = getattr(event, "event", "unknown")
                content: str | None = None
                tool_name: str | None = None

                data = getattr(event, "data", None)
                if event_type == "thread.message.delta" and data:
                    for block in getattr(getattr(data, "delta", None), "content", []) or []:
                        if getattr(block, "type", None) == "text":
                            content = getattr(block.text, "value", None)
                elif event_type == "thread.run.step.delta" and data:
                    step_delta = getattr(data, "delta", None)
                    step_details = getattr(step_delta, "step_details", None) if step_delta else None
                    if step_details and getattr(step_details, "type", None) == "tool_calls":
                        for tc in getattr(step_details, "tool_calls", []) or []:
                            tool_name = getattr(tc, "function", MagicMock()).name if hasattr(tc, "function") else None

                yield AgentSessionEvent(
                    type=event_type,
                    content=content,
                    tool_name=tool_name,
                    raw={},
                )

    async def interrupt(self, session_id: str) -> None:
        thread_id, run_id = self._parse_id(session_id)
        await self._client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
        logger.info("openai_run_cancelled thread_id=%s run_id=%s", thread_id, run_id)
```

Note: The `MagicMock` import in `stream_events` is a stub — replace with proper attribute access before shipping. Fix it now:

```python
# Replace the tool_name line in stream_events with:
tool_name = getattr(getattr(tc, "function", None), "name", None)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_openai_adapter_create_session \
    tests/test_agent_governance.py::test_openai_adapter_get_result_completed \
    tests/test_agent_governance.py::test_openai_adapter_interrupt -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/integrations/adapters/openai_agents.py tests/test_agent_governance.py
git commit -m "feat: add OpenAIAgentsAdapter"
```

---

## Task 6: Adapter Factory and Config

**Files:**
- Modify: `src/pearl/integrations/adapters/__init__.py`
- Modify: `src/pearl/config.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
from pearl.integrations.adapters import get_agent_platform_adapter
from pearl.integrations.adapters.claude_managed_agents import ClaudeManagedAgentsAdapter
from pearl.integrations.adapters.openai_agents import OpenAIAgentsAdapter


def test_get_agent_platform_adapter_claude():
    adapter = get_agent_platform_adapter("claude", api_key="test-key")
    assert isinstance(adapter, ClaudeManagedAgentsAdapter)


def test_get_agent_platform_adapter_openai():
    adapter = get_agent_platform_adapter("openai", api_key="test-key")
    assert isinstance(adapter, OpenAIAgentsAdapter)


def test_get_agent_platform_adapter_unknown():
    with pytest.raises(ValueError, match="Unknown platform"):
        get_agent_platform_adapter("unknown", api_key="test-key")
```

Add config test:
```python
from pearl.config import Settings


def test_settings_has_agent_platform_fields():
    s = Settings(
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
        mass_platform="claude",
        mass_agent_id="agt_01xxx",
        mass_environment_id="env_abc",
    )
    assert s.mass_platform == "claude"
    assert s.mass_agent_id == "agt_01xxx"
    assert s.anthropic_api_key == "sk-ant-test"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_get_agent_platform_adapter_claude \
    tests/test_agent_governance.py::test_get_agent_platform_adapter_openai \
    tests/test_agent_governance.py::test_get_agent_platform_adapter_unknown \
    tests/test_agent_governance.py::test_settings_has_agent_platform_fields -v
```
Expected: `ImportError` or `TypeError`.

- [ ] **Step 3: Add `get_agent_platform_adapter` to `__init__.py`**

Add to the bottom of `src/pearl/integrations/adapters/__init__.py`:
```python
from pearl.integrations.adapters.base_agent import BaseAgentPlatformAdapter


def get_agent_platform_adapter(platform: str, api_key: str) -> BaseAgentPlatformAdapter:
    """Factory: returns the adapter for the given platform string."""
    if platform == "claude":
        from pearl.integrations.adapters.claude_managed_agents import ClaudeManagedAgentsAdapter
        return ClaudeManagedAgentsAdapter(api_key=api_key)
    if platform == "openai":
        from pearl.integrations.adapters.openai_agents import OpenAIAgentsAdapter
        return OpenAIAgentsAdapter(api_key=api_key)
    raise ValueError(f"Unknown platform: {platform!r}")
```

- [ ] **Step 4: Add settings fields to `config.py`**

Add after the `sonar_token` line in `src/pearl/config.py`:
```python
    # Anthropic Claude Managed Agents
    anthropic_api_key: str = ""          # PEARL_ANTHROPIC_API_KEY

    # OpenAI Agents API
    openai_api_key: str = ""             # PEARL_OPENAI_API_KEY

    # MASS 2.0 platform settings
    mass_platform: str = "claude"        # PEARL_MASS_PLATFORM — "claude" | "openai"
    mass_agent_id: str = ""              # PEARL_MASS_AGENT_ID — agt_xxx (Claude) or wf_xxx (OpenAI)
    mass_environment_id: str = ""        # PEARL_MASS_ENVIRONMENT_ID — Claude environment ID
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_get_agent_platform_adapter_claude \
    tests/test_agent_governance.py::test_get_agent_platform_adapter_openai \
    tests/test_agent_governance.py::test_get_agent_platform_adapter_unknown \
    tests/test_agent_governance.py::test_settings_has_agent_platform_fields -v
```
Expected: all 4 pass.

- [ ] **Step 6: Commit**

```bash
git add src/pearl/integrations/adapters/__init__.py src/pearl/config.py tests/test_agent_governance.py
git commit -m "feat: add get_agent_platform_adapter factory + config fields for Claude/OpenAI"
```

---

## Task 7: AgentAssessmentService

**Files:**
- Create: `src/pearl/services/agent_assessment.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch
from pearl.services.agent_assessment import AgentAssessmentService
from pearl.integrations.adapters.base_agent import BaseAgentPlatformAdapter


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

    # Verify AgentSessionRow was created
    from pearl.repositories.agent_session_repo import AgentSessionRepository
    repo = AgentSessionRepository(db_session)
    # Find by platform_session_id
    from sqlalchemy import select
    from pearl.db.models.agent_session import AgentSessionRow
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

    call_kwargs = mock_adapter.create_session.call_args
    assert call_kwargs.kwargs.get("agent_id") == "agt_01testxxx" or \
           call_kwargs.args[0] == "agt_01testxxx"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_assess_definition_creates_session_and_row \
    tests/test_agent_governance.py::test_assess_definition_uses_mass_agent_id -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `agent_assessment.py`**

```python
# src/pearl/services/agent_assessment.py
"""AgentAssessmentService — launches MASS agent sessions to assess agent definitions."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.integrations.adapters.base_agent import BaseAgentPlatformAdapter
from pearl.repositories.agent_session_repo import AgentSessionRepository

logger = logging.getLogger(__name__)

_ASSESSMENT_TASK_TEMPLATE = """\
Assess the following agent definition for security, capability risks, and policy compliance.
Ingest your findings using the PeaRL MCP tools (pearl_ingest_finding, pearl_store_scanner_policy).
When complete, call pearl_complete_assessment with your verdict.

Agent definition:

{definition_yaml}
"""


class AgentAssessmentService:
    def __init__(
        self,
        adapter: BaseAgentPlatformAdapter,
        session: AsyncSession,
        mass_agent_id: str = "",
        mass_environment_id: str | None = None,
    ) -> None:
        self._adapter = adapter
        self._session = session
        self._mass_agent_id = mass_agent_id
        self._mass_environment_id = mass_environment_id

    async def assess_definition(
        self,
        project_id: str,
        definition_id: str,
        platform: str,
        definition_yaml: str,
    ) -> str:
        """Launch a MASS assessment session. Returns the platform_session_id.

        Findings arrive via MCP during the session — no polling needed for findings.
        AgentSessionRow.status is updated by the session status poller.
        """
        task = _ASSESSMENT_TASK_TEMPLATE.format(definition_yaml=definition_yaml)

        platform_session_id = await self._adapter.create_session(
            agent_id=self._mass_agent_id,
            task=task,
            environment_id=self._mass_environment_id,
        )
        logger.info(
            "assessment_session_created definition_id=%s platform=%s session_id=%s",
            definition_id,
            platform,
            platform_session_id,
        )

        session_repo = AgentSessionRepository(self._session)
        await session_repo.create(
            definition_id=definition_id,
            project_id=project_id,
            platform=platform,
            platform_session_id=platform_session_id,
            purpose="assessment",
        )

        return platform_session_id
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_assess_definition_creates_session_and_row \
    tests/test_agent_governance.py::test_assess_definition_uses_mass_agent_id -v
```
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/services/agent_assessment.py tests/test_agent_governance.py
git commit -m "feat: add AgentAssessmentService"
```

---

## Task 8: `POST /agent-definitions` Endpoint

**Files:**
- Create: `src/pearl/api/routes/agent_definitions.py`
- Modify: `src/pearl/api/router.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
import json


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
        json={"git_ref": "abc123"},  # missing git_path, platform, definition
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_post_agent_definition_creates_row \
    tests/test_agent_governance.py::test_post_agent_definition_missing_required_fields -v
```
Expected: `404` (route not registered yet).

- [ ] **Step 3: Create `agent_definitions.py` route**

```python
# src/pearl/api/routes/agent_definitions.py
"""Routes for agent definition registration and assessment."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.api.dependencies import get_current_user, get_db, require_role
from pearl.config import settings
from pearl.integrations.adapters import get_agent_platform_adapter
from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
from pearl.services.agent_assessment import AgentAssessmentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}", tags=["Agent Definitions"])


class AgentDefinitionRequest(BaseModel):
    git_ref: str
    git_path: str
    platform: str                    # "claude" | "openai"
    platform_agent_id: str | None = None
    definition: str                  # raw YAML or JSON string
    environment: str = "dev"


def _extract_capabilities(definition_yaml: str) -> dict:
    """Extract key capabilities from agent definition YAML/JSON string."""
    import yaml
    try:
        data = yaml.safe_load(definition_yaml) or {}
    except Exception:
        return {}

    return {
        "tools": data.get("tools", []),
        "mcp_servers": data.get("mcp_servers", []),
        "model": data.get("model"),
        "callable_agents": data.get("callable_agents", []),
        "skills": data.get("skills", []),
        "system_prompt_hash": hashlib.sha256(
            str(data.get("system_prompt", "")).encode()
        ).hexdigest()[:16] if data.get("system_prompt") else None,
    }


@router.post("/agent-definitions", status_code=202)
async def create_agent_definition(
    project_id: str,
    body: AgentDefinitionRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _user: Any = Depends(require_role("operator")),
) -> dict:
    import yaml
    try:
        definition_dict = yaml.safe_load(body.definition) or {}
    except Exception:
        definition_dict = {"raw": body.definition}

    capabilities = _extract_capabilities(body.definition)

    repo = AgentDefinitionRepository(session)
    row = await repo.create(
        project_id=project_id,
        git_ref=body.git_ref,
        git_path=body.git_path,
        platform=body.platform,
        platform_agent_id=body.platform_agent_id,
        definition=definition_dict,
        capabilities=capabilities,
        environment=body.environment,
        version=body.git_ref,
    )
    await session.commit()

    background_tasks.add_task(
        _run_assessment_background,
        project_id=project_id,
        definition_id=row.agent_definition_id,
        platform=body.platform,
        definition_yaml=body.definition,
    )

    return {
        "definition_id": row.agent_definition_id,
        "status": row.status,
    }


async def _run_assessment_background(
    project_id: str,
    definition_id: str,
    platform: str,
    definition_yaml: str,
) -> None:
    """Background task: launch MASS assessment session."""
    from pearl.db.session import async_session_factory
    if not settings.mass_agent_id:
        logger.warning(
            "MASS_AGENT_ID not configured — skipping assessment for definition_id=%s",
            definition_id,
        )
        return

    api_key = (
        settings.anthropic_api_key if platform == "claude" else settings.openai_api_key
    )
    if not api_key:
        logger.warning(
            "No API key configured for platform=%s — skipping assessment definition_id=%s",
            platform,
            definition_id,
        )
        return

    adapter = get_agent_platform_adapter(platform, api_key=api_key)

    try:
        async with async_session_factory() as session:
            service = AgentAssessmentService(
                adapter=adapter,
                session=session,
                mass_agent_id=settings.mass_agent_id,
                mass_environment_id=settings.mass_environment_id or None,
            )
            await service.assess_definition(
                project_id=project_id,
                definition_id=definition_id,
                platform=platform,
                definition_yaml=definition_yaml,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "assessment_background_failed definition_id=%s", definition_id
        )
```

- [ ] **Step 4: Register route in `router.py`**

Add import at top of `src/pearl/api/router.py` import block:
```python
    agent_definitions,
```

Add include after another project-scoped route (e.g., after `allowance_profiles`):
```python
api_router.include_router(agent_definitions.router)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_post_agent_definition_creates_row \
    tests/test_agent_governance.py::test_post_agent_definition_missing_required_fields -v
```
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add src/pearl/api/routes/agent_definitions.py src/pearl/api/router.py tests/test_agent_governance.py
git commit -m "feat: add POST /projects/{id}/agent-definitions endpoint"
```

---

## Task 9: Gate Rule `agent_definition_assessed`

**Files:**
- Modify: `src/pearl/services/promotion/gate_evaluator.py`
- Test: `tests/test_agent_governance.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_governance.py`:
```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_eval_context_has_agent_definition_fields \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_approved \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_rejected \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_pending \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_no_definition -v
```
Expected: `AttributeError` or `ImportError`.

- [ ] **Step 3: Add fields to `_EvalContext`**

In `src/pearl/services/promotion/gate_evaluator.py`, after the `mass_verdict_risk_level` line (line 315), add:
```python
        # Agent definition governance
        self.agent_definition_id: str | None = None
        self.agent_definition_status: str | None = None  # "pending_assessment" | "assessed" | "approved" | "rejected"
```

- [ ] **Step 4: Add `_eval_agent_definition_assessed` function**

In `gate_evaluator.py`, add this function in the same location as other `_eval_*` functions:
```python
def _eval_agent_definition_assessed(rule: dict, ctx: "_EvalContext") -> tuple[bool, str, dict]:
    """Gate rule: blocks promotion if agent definition is not approved."""
    if ctx.agent_definition_id is None:
        return True, "No agent definition — non-agent project", {}
    if ctx.agent_definition_status == "approved":
        return True, f"Agent definition {ctx.agent_definition_id} approved", {}
    if ctx.agent_definition_status == "rejected":
        return False, f"Agent definition {ctx.agent_definition_id} rejected by MASS assessment", {}
    return False, f"Agent definition {ctx.agent_definition_id} pending assessment", {}
```

- [ ] **Step 5: Wire rule into rule dispatch**

Find the rule dispatch in `gate_evaluator.py` — look for a dict mapping rule type strings to handler functions or a series of `if rule_type == "..."` checks. Add:
```python
"agent_definition_assessed": _eval_agent_definition_assessed,
```
(if dict) or:
```python
elif rule_type == "agent_definition_assessed":
    return _eval_agent_definition_assessed(rule, ctx)
```
(if if/elif chain)

- [ ] **Step 6: Load agent definition status in `_build_eval_context`**

In `_build_eval_context`, after the Cedar deployment block (around line 540), add:
```python
    # Agent definition governance — latest definition for this project + environment
    try:
        from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
        agent_def_repo = AgentDefinitionRepository(session)
        agent_def = await agent_def_repo.get_latest_for_project(
            project_id, environment=target_env or "dev"
        )
        if agent_def:
            ctx.agent_definition_id = agent_def.agent_definition_id
            ctx.agent_definition_status = agent_def.status
    except Exception:
        pass  # non-agent projects have no definition — ctx fields stay None
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_agent_governance.py::test_eval_context_has_agent_definition_fields \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_approved \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_rejected \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_pending \
    tests/test_agent_governance.py::test_agent_definition_assessed_rule_no_definition -v
```
Expected: all 5 pass.

- [ ] **Step 8: Run full test suite to check for regressions**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```
Expected: 1 failed 0 (or the pre-existing unrelated failures only). If new failures appear, investigate before committing.

- [ ] **Step 9: Commit**

```bash
git add src/pearl/services/promotion/gate_evaluator.py tests/test_agent_governance.py
git commit -m "feat: add agent_definition_assessed gate rule + _EvalContext fields"
```

---

## Task 10: Deprecate MASS Bridge

> **Note:** Only execute this task after MASS 2.0 is confirmed running as a Managed Agent and the platform session flow is tested end-to-end (see spec Migration Path step 8). Do not delete before that confirmation.

**Files:**
- Delete: `src/pearl/scanning/mass_bridge.py`
- Test: run full suite after deletion

- [ ] **Step 1: Verify nothing imports mass_bridge**

```bash
grep -r "mass_bridge" src/ tests/
```
Expected: only files in `scanning/` and any direct import in `scanning.py`. If other files import it, update them first.

- [ ] **Step 2: Check scanning.py for MassClient usage**

```bash
grep -n "MassClient\|mass_bridge" src/pearl/api/routes/scanning.py
```
If any references remain, replace them with a comment: `# MassClient removed — findings arrive via PeaRL MCP tools during MASS agent session`

- [ ] **Step 3: Delete mass_bridge.py**

```bash
git rm src/pearl/scanning/mass_bridge.py
```

- [ ] **Step 4: Run full test suite**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```
Expected: no new failures introduced by the deletion.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: remove MassClient / mass_bridge.py — replaced by AgentAssessmentService"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| `agent_definitions` table (migration 007) | Task 1 |
| `agent_sessions` table (migration 008) | Task 1 |
| `AgentDefinitionRepository`, `AgentSessionRepository` | Task 2 |
| `BaseAgentPlatformAdapter` + `AgentSessionResult` + `AgentSessionEvent` | Task 3 |
| `ClaudeManagedAgentsAdapter` | Task 4 |
| `OpenAIAgentsAdapter` | Task 5 |
| `get_agent_platform_adapter` factory | Task 6 |
| Settings: `anthropic_api_key`, `openai_api_key`, `mass_platform`, `mass_agent_id`, `mass_environment_id` | Task 6 |
| `AgentAssessmentService` (replaces `MassClient`) | Task 7 |
| `POST /projects/{id}/agent-definitions` endpoint | Task 8 |
| `agent_definition_assessed` gate rule | Task 9 |
| `_EvalContext` additions | Task 9 |
| `mass_bridge.py` deprecation | Task 10 |
| `def_` prefix for AgentDefinition IDs | Task 2 (repo uses `generate_id("def")`) |
| `ses_` prefix for AgentSession IDs | Task 2 (repo uses `generate_id("ses")`) |

All spec requirements covered.

### Type consistency

- `create_session(agent_id, task, environment_id=None) -> str` — matches spec + adapters
- `get_result(session_id) -> AgentSessionResult` — consistent across Tasks 3/4/5
- `AgentAssessmentService.assess_definition(project_id, definition_id, platform, definition_yaml) -> str` — matches Task 7 + Task 8 BackgroundTask call

### No placeholders

Verified: no TBD/TODO in any code block. All steps include exact code.
