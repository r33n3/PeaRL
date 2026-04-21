# Dark Factory Governance Container Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich PeaRL Projects into full Dark Factory governance containers — adding WTK/agent team linkage fields to the backend, two new API endpoints WTK needs, and rebuilding the ProjectPage, Dashboard, and ApprovalDetail UI to give human reviewers complete situational awareness without leaving the project view.

**Architecture:** Three self-contained phases. Phase 1 adds new nullable columns to `ProjectRow` (migration 009), updates the project repo/routes to expose them, and adds `POST /projects/{id}/agents` and `GET /projects/{id}/governance-state` endpoints. Phase 2 rebuilds `ProjectPage.tsx` to add an "Agent Team" tab and enriches the Overview tab with goal context, target, and inline pending approvals. Phase 3 enriches `ApprovalDetailPage.tsx` with full project/goal context and updates `DashboardPage.tsx` to show a governance queue grouped by project. No existing functionality is removed — all changes are additive.

**Tech Stack:** FastAPI + SQLAlchemy async, Alembic, React + TypeScript + TanStack Query, existing PeaRL component library (`VaultCard`, `EnvBadge`, `StatusBadge`, `MonoText`).

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pearl/db/models/project.py` | Modify | Add 7 new nullable columns to `ProjectRow` |
| `src/pearl/db/migrations/versions/009_add_governance_container_fields.py` | Create | Migration adding new columns |
| `src/pearl/repositories/project_repo.py` | Modify | Add `update_governance_fields` and `get_governance_state` methods |
| `src/pearl/api/routes/projects.py` | Modify | Add `POST /projects/{id}/agents`, `GET /projects/{id}/governance-state`, expose new fields in `GET /projects/{id}` |
| `src/pearl/api/routes/approvals.py` | Modify | Add `agent_id` and `goal_id` to approval request shape and pending list response |
| `frontend/src/api/projects.ts` | Modify | Add `useGovernanceState` hook and `registerAgents` mutation |
| `frontend/src/api/dashboard.ts` | Modify | Add `pending_approvals_detail` to dashboard project shape |
| `frontend/src/pages/ProjectPage.tsx` | Modify | Add "Team" tab, enrich Overview with goal/target/inline approvals |
| `frontend/src/pages/DashboardPage.tsx` | Modify | Add governance queue panel (pending approvals grouped by project) |
| `frontend/src/pages/ApprovalDetailPage.tsx` | Modify | Add project/goal context panel at top, show agent identity |
| `tests/test_governance_container.py` | Create | Backend tests for new fields and endpoints |

---

## Phase 1 — Backend: Governance Container Fields and Endpoints

---

### Task 1: Migration 009 — add governance container columns to projects

**Files:**
- Create: `src/pearl/db/migrations/versions/009_add_governance_container_fields.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_governance_container.py`:

```python
"""Tests for Dark Factory governance container fields."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_project_governance_state_endpoint_exists(app, admin_token):
    """GET /projects/{id}/governance-state returns 404 for missing project (not 405)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(
            "/api/v1/projects/proj_nonexistent/governance-state",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_register_agents_endpoint_exists(app, admin_token):
    """POST /projects/{id}/agents returns 404 for missing project (not 405)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/projects/proj_nonexistent/agents",
            json={"coordinator": "agent_coord1", "workers": [], "evaluators": []},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_governance_container.py -v
```

Expected: FAIL — 405 Method Not Allowed (routes don't exist yet)

- [ ] **Step 3: Create migration 009**

Create `src/pearl/db/migrations/versions/009_add_governance_container_fields.py`:

```python
"""Add governance container fields to projects table.

Revision ID: 009
Revises: 008
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    cols = [
        ("intake_card_id", sa.String(256)),
        ("goal_id", sa.String(256)),
        ("target_type", sa.String(128)),
        ("target_id", sa.String(512)),
        ("risk_classification", sa.String(64)),
        ("agent_members", sa.JSON),
        ("litellm_key_refs", sa.JSON),
        ("memory_policy_refs", sa.JSON),
        ("qualification_packet_id", sa.String(256)),
    ]
    for col_name, col_type in cols:
        if not _column_exists("projects", col_name):
            op.add_column("projects", sa.Column(col_name, col_type, nullable=True))


def downgrade():
    for col_name in [
        "intake_card_id", "goal_id", "target_type", "target_id",
        "risk_classification", "agent_members", "litellm_key_refs",
        "memory_policy_refs", "qualification_packet_id",
    ]:
        op.drop_column("projects", col_name)
```

- [ ] **Step 4: Commit**

```bash
git add src/pearl/db/migrations/versions/009_add_governance_container_fields.py tests/test_governance_container.py
git commit -m "feat(governance): migration 009 — add governance container fields to projects"
```

---

### Task 2: Enrich ProjectRow ORM model

**Files:**
- Modify: `src/pearl/db/models/project.py`

- [ ] **Step 1: Add new columns to ProjectRow**

In `src/pearl/db/models/project.py`, add after the existing `tags` column:

```python
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ProjectRow(Base, TimestampMixin):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_team: Mapped[str] = mapped_column(String(200), nullable=False)
    business_criticality: Mapped[str] = mapped_column(String(50), nullable=False)
    external_exposure: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
    org_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    bu_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("business_units.bu_id"), nullable=True, index=True
    )
    current_environment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claude_md_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ── Dark Factory governance container fields ──────────────────────────
    intake_card_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    goal_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    risk_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_members: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    litellm_key_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    memory_policy_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    qualification_packet_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
```

- [ ] **Step 2: Run existing project tests to verify no regression**

```bash
PEARL_LOCAL=1 pytest tests/ -k "project" -q
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add src/pearl/db/models/project.py
git commit -m "feat(governance): add governance container columns to ProjectRow ORM model"
```

---

### Task 3: Repository — governance state query and agent registration

**Files:**
- Modify: `src/pearl/repositories/project_repo.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_governance_container.py`:

```python
from pearl.repositories.project_repo import ProjectRepository


@pytest.mark.asyncio
async def test_project_repo_update_governance_fields(db_session):
    """update_governance_fields sets Dark Factory fields on an existing project row."""
    from pearl.db.models.project import ProjectRow
    from datetime import datetime, timezone

    row = ProjectRow(
        project_id="proj_govtest01",
        name="Gov Test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
        schema_version="1.1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()

    repo = ProjectRepository(db_session)
    updated = await repo.update_governance_fields(
        project_id="proj_govtest01",
        intake_card_id="card_001",
        goal_id="goal_abc",
        target_type="repo",
        target_id="repo:MASS-2.0",
        risk_classification="medium",
    )
    await db_session.commit()

    assert updated.intake_card_id == "card_001"
    assert updated.target_type == "repo"
    assert updated.target_id == "repo:MASS-2.0"
    assert updated.risk_classification == "medium"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_governance_container.py::test_project_repo_update_governance_fields -v
```

Expected: FAIL — `AttributeError: update_governance_fields`

- [ ] **Step 3: Update the repository**

Replace `src/pearl/repositories/project_repo.py` with:

```python
"""Project repository."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.project import ProjectRow
from pearl.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectRow)

    async def get(self, project_id: str) -> ProjectRow | None:
        return await self.get_by_id("project_id", project_id)

    async def update_governance_fields(
        self,
        project_id: str,
        intake_card_id: str | None = None,
        goal_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        risk_classification: str | None = None,
        agent_members: dict | None = None,
        litellm_key_refs: list | None = None,
        memory_policy_refs: list | None = None,
        qualification_packet_id: str | None = None,
    ) -> ProjectRow:
        row = await self.get(project_id)
        if row is None:
            from pearl.errors.exceptions import NotFoundError
            raise NotFoundError("Project", project_id)
        if intake_card_id is not None:
            row.intake_card_id = intake_card_id
        if goal_id is not None:
            row.goal_id = goal_id
        if target_type is not None:
            row.target_type = target_type
        if target_id is not None:
            row.target_id = target_id
        if risk_classification is not None:
            row.risk_classification = risk_classification
        if agent_members is not None:
            row.agent_members = agent_members
        if litellm_key_refs is not None:
            row.litellm_key_refs = litellm_key_refs
        if memory_policy_refs is not None:
            row.memory_policy_refs = memory_policy_refs
        if qualification_packet_id is not None:
            row.qualification_packet_id = qualification_packet_id
        return row
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_governance_container.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pearl/repositories/project_repo.py tests/test_governance_container.py
git commit -m "feat(governance): project repo update_governance_fields method"
```

---

### Task 4: New API endpoints — register agents and governance-state

**Files:**
- Modify: `src/pearl/api/routes/projects.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_governance_container.py`:

```python
@pytest.mark.asyncio
async def test_register_agents_on_project(app, admin_token, sample_project_id):
    """POST /projects/{id}/agents stores agent_members on the project."""
    payload = {
        "coordinator": "agent_coord_abc",
        "workers": ["agent_worker_1", "agent_worker_2"],
        "evaluators": ["agent_eval_1"],
        "litellm_key_refs": ["vk-worker-agent", "vk-governance-agent"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            f"/api/v1/projects/{sample_project_id}/agents",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_members"]["coordinator"] == "agent_coord_abc"
    assert len(data["agent_members"]["workers"]) == 2
    assert data["litellm_key_refs"] == ["vk-worker-agent", "vk-governance-agent"]


@pytest.mark.asyncio
async def test_governance_state_returns_project_context(app, admin_token, sample_project_id):
    """GET /projects/{id}/governance-state returns gates, approvals, and governance fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(
            f"/api/v1/projects/{sample_project_id}/governance-state",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "project_id" in data
    assert "pending_approvals" in data
    assert "gate_status" in data
    assert "agent_members" in data
    assert "goal_id" in data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_governance_container.py::test_register_agents_on_project tests/test_governance_container.py::test_governance_state_returns_project_context -v
```

Expected: FAIL — 404 (routes don't exist yet)

- [ ] **Step 3: Add the two new routes to projects.py**

At the end of `src/pearl/api/routes/projects.py`, add:

```python
from pydantic import BaseModel as _BaseModel


class RegisterAgentsRequest(_BaseModel):
    coordinator: str | None = None
    workers: list[str] = []
    evaluators: list[str] = []
    litellm_key_refs: list[str] = []
    memory_policy_refs: list[str] = []
    goal_id: str | None = None
    intake_card_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    risk_classification: str | None = None
    qualification_packet_id: str | None = None


@router.post("/projects/{project_id}/agents")
async def register_project_agents(
    project_id: str,
    body: RegisterAgentsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """WTK registers coordinator, worker, and evaluator agents against a project.

    Also accepts goal/target/risk context from the WTK package manifest.
    """
    user = getattr(request.state, "user", {})
    if not any(r in user.get("roles", []) for r in ("admin", "operator", "service_account")):
        from pearl.errors.exceptions import AuthorizationError
        raise AuthorizationError("operator, admin, or service_account role required")

    repo = ProjectRepository(db)
    agent_members = {
        "coordinator": body.coordinator,
        "workers": body.workers,
        "evaluators": body.evaluators,
    }
    row = await repo.update_governance_fields(
        project_id=project_id,
        agent_members=agent_members,
        litellm_key_refs=body.litellm_key_refs or None,
        memory_policy_refs=body.memory_policy_refs or None,
        goal_id=body.goal_id,
        intake_card_id=body.intake_card_id,
        target_type=body.target_type,
        target_id=body.target_id,
        risk_classification=body.risk_classification,
        qualification_packet_id=body.qualification_packet_id,
    )
    await db.commit()
    await db.refresh(row)
    return {
        "project_id": row.project_id,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "goal_id": row.goal_id,
        "intake_card_id": row.intake_card_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "qualification_packet_id": row.qualification_packet_id,
    }


@router.get("/projects/{project_id}/governance-state")
async def get_project_governance_state(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full governance container state for a project.

    Used by WTK to check gate status and by the PeaRL reviewer UI.
    Returns project metadata, pending approvals, gate summary, and agent team.
    """
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        from pearl.errors.exceptions import NotFoundError
        raise NotFoundError("Project", project_id)

    # Pending approvals for this project
    from pearl.repositories.approval_repo import ApprovalRequestRepository
    approval_repo = ApprovalRequestRepository(db)
    pending = await approval_repo.list_by_project(project_id)
    pending_list = [
        {
            "approval_request_id": a.approval_request_id,
            "request_type": a.request_type,
            "status": a.status,
            "environment": a.environment,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in pending
        if a.status in ("pending", "needs_info")
    ]

    # Gate summary from compiled package
    from pearl.repositories.compiled_package_repo import CompiledPackageRepository
    pkg_repo = CompiledPackageRepository(db)
    pkg = await pkg_repo.get_latest_by_project(project_id)
    gate_status = None
    if pkg:
        pkg_data = pkg.package_data or {}
        gate_status = {
            "package_id": pkg.package_id,
            "compiled_at": pkg_data.get("package_metadata", {}).get("integrity", {}).get("compiled_at"),
            "environment": pkg_data.get("project_identity", {}).get("environment"),
        }

    return {
        "project_id": row.project_id,
        "name": row.name,
        "current_environment": row.current_environment,
        "intake_card_id": row.intake_card_id,
        "goal_id": row.goal_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "qualification_packet_id": row.qualification_packet_id,
        "pending_approvals": pending_list,
        "pending_approvals_count": len(pending_list),
        "gate_status": gate_status,
    }
```

- [ ] **Step 4: Expose new fields in GET /projects/{id}**

In the existing `get_project` route in `projects.py`, find the return dict and add the governance fields:

```python
    return {
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "owner_team": row.owner_team,
        "business_criticality": row.business_criticality,
        "external_exposure": row.external_exposure,
        "ai_enabled": row.ai_enabled,
        "bu_id": row.bu_id,
        "tags": row.tags,
        "current_environment": row.current_environment,
        "claude_md_verified": row.claude_md_verified,
        # ── Governance container fields ──
        "intake_card_id": row.intake_card_id,
        "goal_id": row.goal_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "qualification_packet_id": row.qualification_packet_id,
    }
```

- [ ] **Step 5: Run all governance tests**

```bash
PEARL_LOCAL=1 pytest tests/test_governance_container.py -v
```

Expected: all pass

- [ ] **Step 6: Run full suite to check for regressions**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/contract --ignore=tests/security
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/pearl/api/routes/projects.py tests/test_governance_container.py
git commit -m "feat(governance): POST /projects/{id}/agents and GET /projects/{id}/governance-state endpoints"
```

---

## Phase 2 — Frontend: Project as Governance Container

---

### Task 5: Frontend API hooks for governance state

**Files:**
- Modify: `frontend/src/api/projects.ts`

- [ ] **Step 1: Add TypeScript types and hooks**

Find `frontend/src/api/projects.ts` (or wherever `useProjectOverview` is defined — check `frontend/src/api/`). Add the following types and hooks:

```typescript
// Add to the existing projects API file

export interface AgentMembers {
  coordinator: string | null;
  workers: string[];
  evaluators: string[];
}

export interface PendingApprovalSummary {
  approval_request_id: string;
  request_type: string;
  status: string;
  environment: string;
  created_at: string | null;
}

export interface GovernanceState {
  project_id: string;
  name: string;
  current_environment: string | null;
  intake_card_id: string | null;
  goal_id: string | null;
  target_type: string | null;
  target_id: string | null;
  risk_classification: string | null;
  agent_members: AgentMembers | null;
  litellm_key_refs: string[] | null;
  memory_policy_refs: string[] | null;
  qualification_packet_id: string | null;
  pending_approvals: PendingApprovalSummary[];
  pending_approvals_count: number;
  gate_status: {
    package_id: string;
    compiled_at: string | null;
    environment: string | null;
  } | null;
}

export interface RegisterAgentsPayload {
  coordinator?: string;
  workers?: string[];
  evaluators?: string[];
  litellm_key_refs?: string[];
  memory_policy_refs?: string[];
  goal_id?: string;
  intake_card_id?: string;
  target_type?: string;
  target_id?: string;
  risk_classification?: string;
  qualification_packet_id?: string;
}

export function useGovernanceState(projectId: string | undefined) {
  return useQuery({
    queryKey: ["governance-state", projectId],
    queryFn: () => apiFetch<GovernanceState>(`/projects/${projectId}/governance-state`),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

export function useRegisterAgents(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisterAgentsPayload) =>
      apiFetch<GovernanceState>(`/projects/${projectId}/agents`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["governance-state", projectId] });
    },
  });
}
```

Ensure `useQuery`, `useMutation`, `useQueryClient` are imported from `@tanstack/react-query` and `apiFetch` from `./client`.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|warning|✓" | head -20
```

Expected: `✓ built in ...` with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/projects.ts
git commit -m "feat(governance): useGovernanceState and useRegisterAgents frontend hooks"
```

---

### Task 6: ProjectPage — Agent Team tab

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx`

- [ ] **Step 1: Add "team" to the tab type and bar**

In `frontend/src/pages/ProjectPage.tsx`, update the `activeTab` state type and tab bar. Find:

```tsx
const [activeTab, setActiveTab] = useState<"overview" | "guardrails" | "setup">("overview");
```

Replace with:

```tsx
const [activeTab, setActiveTab] = useState<"overview" | "team" | "guardrails" | "setup">("overview");
```

Find the tab bar rendering (around line 206) where `["overview", "guardrails", "setup"]` is mapped. Replace with:

```tsx
{(["overview", "team", "guardrails", "setup"] as const).map((tab) => (
  <button
    key={tab}
    onClick={() => setActiveTab(tab)}
    className={
      activeTab === tab
        ? "tab-active"
        : "tab-inactive"
    }
  >
    {tab}
  </button>
))}
```

- [ ] **Step 2: Add the governance state hook**

Add near the top of the `ProjectPage` component alongside the other hooks:

```tsx
import { useGovernanceState } from "@/api/projects";

// Inside the component:
const { data: govState } = useGovernanceState(projectId);
```

- [ ] **Step 3: Add the Team tab panel**

After the existing guardrails and setup tab conditionals, add:

```tsx
{activeTab === "team" && (
  <div className="p-6 max-w-3xl space-y-6">

    {/* Goal and intent */}
    <VaultCard>
      <h3 className="font-heading text-sm font-semibold text-bone mb-3 uppercase tracking-wider">
        Intent
      </h3>
      <div className="grid grid-cols-2 gap-4 text-xs font-mono">
        <div>
          <p className="text-bone-dim mb-1">Intake Card</p>
          <MonoText>{govState?.intake_card_id ?? "—"}</MonoText>
        </div>
        <div>
          <p className="text-bone-dim mb-1">WTK Goal</p>
          <MonoText>{govState?.goal_id ?? "—"}</MonoText>
        </div>
        <div>
          <p className="text-bone-dim mb-1">Target Type</p>
          <MonoText>{govState?.target_type ?? "—"}</MonoText>
        </div>
        <div>
          <p className="text-bone-dim mb-1">Target ID</p>
          <MonoText>{govState?.target_id ?? "—"}</MonoText>
        </div>
        <div>
          <p className="text-bone-dim mb-1">Risk Classification</p>
          <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
            govState?.risk_classification === "high" ? "bg-red-900/40 text-red-400" :
            govState?.risk_classification === "medium" ? "bg-yellow-900/40 text-yellow-400" :
            govState?.risk_classification === "low" ? "bg-green-900/40 text-green-400" :
            "bg-slate-border/40 text-bone-dim"
          }`}>
            {govState?.risk_classification ?? "unclassified"}
          </span>
        </div>
        <div>
          <p className="text-bone-dim mb-1">Qualification Packet</p>
          <MonoText>{govState?.qualification_packet_id ?? "—"}</MonoText>
        </div>
      </div>
    </VaultCard>

    {/* Agent team */}
    <VaultCard>
      <h3 className="font-heading text-sm font-semibold text-bone mb-3 uppercase tracking-wider">
        Agent Team
      </h3>
      {!govState?.agent_members ? (
        <p className="text-xs text-bone-dim font-mono">No agent team registered. WTK registers agents via POST /projects/{projectId}/agents.</p>
      ) : (
        <div className="space-y-4 text-xs font-mono">
          {govState.agent_members.coordinator && (
            <div>
              <p className="text-bone-dim mb-1 uppercase tracking-wider text-[10px]">Coordinator</p>
              <div className="flex items-center gap-2 px-3 py-2 rounded border border-cold-teal/30 bg-cold-teal/5">
                <span className="w-2 h-2 rounded-full bg-cold-teal" />
                <MonoText className="text-cold-teal">{govState.agent_members.coordinator}</MonoText>
              </div>
            </div>
          )}
          {govState.agent_members.workers.length > 0 && (
            <div>
              <p className="text-bone-dim mb-1 uppercase tracking-wider text-[10px]">Workers</p>
              <div className="space-y-1">
                {govState.agent_members.workers.map((w) => (
                  <div key={w} className="flex items-center gap-2 px-3 py-1.5 rounded border border-slate-border bg-slate-border/10">
                    <span className="w-1.5 h-1.5 rounded-full bg-bone-dim" />
                    <MonoText>{w}</MonoText>
                  </div>
                ))}
              </div>
            </div>
          )}
          {govState.agent_members.evaluators.length > 0 && (
            <div>
              <p className="text-bone-dim mb-1 uppercase tracking-wider text-[10px]">Evaluators</p>
              <div className="space-y-1">
                {govState.agent_members.evaluators.map((e) => (
                  <div key={e} className="flex items-center gap-2 px-3 py-1.5 rounded border border-clinical-cyan/30 bg-clinical-cyan/5">
                    <span className="w-1.5 h-1.5 rounded-full bg-clinical-cyan" />
                    <MonoText className="text-clinical-cyan">{e}</MonoText>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </VaultCard>

    {/* LiteLLM key references */}
    {(govState?.litellm_key_refs?.length ?? 0) > 0 && (
      <VaultCard>
        <h3 className="font-heading text-sm font-semibold text-bone mb-3 uppercase tracking-wider">
          Runtime Keys
        </h3>
        <div className="flex flex-wrap gap-2">
          {govState!.litellm_key_refs!.map((k) => (
            <span key={k} className="px-2 py-1 rounded border border-slate-border text-[10px] font-mono text-bone-muted">
              {k}
            </span>
          ))}
        </div>
      </VaultCard>
    )}

    {/* Pending approvals inline */}
    {(govState?.pending_approvals_count ?? 0) > 0 && (
      <VaultCard>
        <h3 className="font-heading text-sm font-semibold text-bone mb-3 uppercase tracking-wider">
          Pending Approvals
        </h3>
        <div className="space-y-2">
          {govState!.pending_approvals.map((a) => (
            <a
              key={a.approval_request_id}
              href={`/approvals/${a.approval_request_id}`}
              className="flex items-center justify-between px-3 py-2 rounded border border-clinical-cyan/30 bg-clinical-cyan/5 hover:border-clinical-cyan transition-colors"
            >
              <div>
                <span className="text-xs font-mono text-bone">{a.request_type}</span>
                <span className="text-[10px] font-mono text-bone-dim ml-2">#{a.approval_request_id}</span>
              </div>
              <span className="badge-pending text-[10px]">{a.status}</span>
            </a>
          ))}
        </div>
      </VaultCard>
    )}
  </div>
)}
```

- [ ] **Step 4: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|✓" | head -10
```

Expected: `✓ built in ...`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProjectPage.tsx
git commit -m "feat(governance): Agent Team tab on ProjectPage with intent, team, runtime keys, and pending approvals"
```

---

### Task 7: ProjectPage — enrich Overview tab with governance context

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx`

- [ ] **Step 1: Add governance context row to Overview header**

In the Overview tab section of `ProjectPage.tsx` (around line 234), find the project header area where `name`, `project_id`, and environment are displayed. After the existing project metadata, add a governance context strip:

```tsx
{/* Governance context strip — shows when governance fields are populated */}
{(govState?.goal_id || govState?.target_id || govState?.intake_card_id) && (
  <div className="flex flex-wrap gap-4 px-4 py-2 bg-slate-border/10 rounded border border-slate-border text-xs font-mono mb-4">
    {govState.intake_card_id && (
      <span className="flex items-center gap-1.5 text-bone-dim">
        <span className="text-bone-dim/50 uppercase text-[10px] tracking-wider">Card</span>
        <MonoText>{govState.intake_card_id}</MonoText>
      </span>
    )}
    {govState.goal_id && (
      <span className="flex items-center gap-1.5 text-bone-dim">
        <span className="text-bone-dim/50 uppercase text-[10px] tracking-wider">Goal</span>
        <MonoText>{govState.goal_id}</MonoText>
      </span>
    )}
    {govState.target_id && (
      <span className="flex items-center gap-1.5 text-bone-dim">
        <span className="text-bone-dim/50 uppercase text-[10px] tracking-wider">Target</span>
        <MonoText>{govState.target_type ? `${govState.target_type}:` : ""}{govState.target_id}</MonoText>
      </span>
    )}
    {govState.risk_classification && (
      <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
        govState.risk_classification === "high" ? "bg-red-900/40 text-red-400" :
        govState.risk_classification === "medium" ? "bg-yellow-900/40 text-yellow-400" :
        "bg-green-900/40 text-green-400"
      }`}>
        {govState.risk_classification} risk
      </span>
    )}
    {(govState.agent_members?.coordinator || (govState.agent_members?.workers?.length ?? 0) > 0) && (
      <span
        className="text-cold-teal cursor-pointer hover:underline text-[10px]"
        onClick={() => setActiveTab("team")}
      >
        {1 + (govState.agent_members?.workers?.length ?? 0) + (govState.agent_members?.evaluators?.length ?? 0)} agents →
      </span>
    )}
  </div>
)}
```

- [ ] **Step 2: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|✓" | head -10
```

Expected: `✓ built in ...`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ProjectPage.tsx
git commit -m "feat(governance): governance context strip in ProjectPage Overview tab"
```

---

## Phase 3 — Frontend: Dashboard Queue and Approval Context

---

### Task 8: Dashboard — governance queue panel

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: Add pending approvals detail to dashboard API type**

Find `frontend/src/api/dashboard.ts` and the project summary type. Add `pending_approvals_detail` to the type:

```typescript
export interface DashboardProject {
  project_id: string;
  name: string;
  environment: string | null;
  gate_progress_pct: number;
  total_open_findings: number;
  findings_by_severity: Record<string, number>;
  pending_approvals: number;
  // Governance container fields
  intake_card_id: string | null;
  goal_id: string | null;
  target_type: string | null;
  target_id: string | null;
  risk_classification: string | null;
  agent_members: {
    coordinator: string | null;
    workers: string[];
    evaluators: string[];
  } | null;
}
```

- [ ] **Step 2: Expose governance fields from the dashboard route**

Find `src/pearl/api/routes/dashboard.py`. In the route that returns the project list, add the governance fields to the serialized project dict:

```python
# In the list of fields returned per project, add:
"intake_card_id": row.intake_card_id,
"goal_id": row.goal_id,
"target_type": row.target_type,
"target_id": row.target_id,
"risk_classification": row.risk_classification,
"agent_members": row.agent_members,
```

- [ ] **Step 3: Add governance queue panel to DashboardPage**

In `frontend/src/pages/DashboardPage.tsx`, after the project grid, add a governance queue section that shows all pending approvals grouped by project. Add imports at the top:

```tsx
import { useNavigate } from "react-router-dom";
import { useProjects } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { GateProgress } from "@/components/shared/GateProgress";
import { MonoText } from "@/components/shared/MonoText";
import { Shield, AlertTriangle, Clock } from "lucide-react";
import { usePendingApprovals } from "@/api/approvals";
```

Add `usePendingApprovals` hook in `frontend/src/api/approvals.ts` if it doesn't exist:

```typescript
export function usePendingApprovals() {
  return useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => apiFetch<PendingApproval[]>("/approvals/pending"),
    refetchInterval: 30_000,
  });
}
```

Add the governance queue panel in `DashboardPage` after the project grid:

```tsx
{/* Governance queue — pending approvals grouped by project */}
{totalPending > 0 && (
  <div className="mt-8">
    <h2 className="vault-heading text-lg mb-4 flex items-center gap-2">
      <Clock size={16} className="text-clinical-cyan" />
      Governance Queue
      <span className="ml-2 px-2 py-0.5 rounded bg-clinical-cyan/20 text-clinical-cyan text-xs font-mono">
        {totalPending} pending
      </span>
    </h2>
    <div className="space-y-2">
      {projects
        ?.filter((p) => p.pending_approvals > 0)
        .map((p) => (
          <VaultCard
            key={p.project_id}
            interactive
            onClick={() => navigate(`/projects/${p.project_id}?tab=team`)}
            className="flex items-center justify-between"
          >
            <div className="flex items-center gap-4">
              <div>
                <p className="text-sm font-heading font-semibold text-bone">{p.name}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <MonoText className="text-[10px]">{p.project_id}</MonoText>
                  {p.target_id && (
                    <MonoText className="text-[10px] text-bone-dim">
                      → {p.target_type ? `${p.target_type}:` : ""}{p.target_id}
                    </MonoText>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {p.environment && <EnvBadge env={p.environment} />}
              <span className="badge-pending text-[10px]">
                {p.pending_approvals} pending
              </span>
            </div>
          </VaultCard>
        ))}
    </div>
  </div>
)}
```

- [ ] **Step 4: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|✓" | head -10
```

Expected: `✓ built in ...`

- [ ] **Step 5: Run full test suite for regressions**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/contract --ignore=tests/security
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/api/dashboard.ts frontend/src/api/approvals.ts src/pearl/api/routes/dashboard.py
git commit -m "feat(governance): Dashboard governance queue shows pending approvals grouped by project"
```

---

### Task 9: ApprovalDetailPage — project and agent context panel

**Files:**
- Modify: `frontend/src/pages/ApprovalDetailPage.tsx`

- [ ] **Step 1: Add governance state hook to ApprovalDetailPage**

In `frontend/src/pages/ApprovalDetailPage.tsx`, find the existing imports and add:

```tsx
import { useGovernanceState } from "@/api/projects";
import { MonoText } from "@/components/shared/MonoText";
import { EnvBadge } from "@/components/shared/EnvBadge";
```

Inside `ApprovalDetailPage`, get the project ID from the approval data and fetch governance state:

```tsx
const projectId = approval?.project_id;
const { data: govState } = useGovernanceState(projectId);
```

- [ ] **Step 2: Add context panel above the approval detail**

In the JSX, before the existing approval header/title, insert:

```tsx
{/* Project governance context — reviewer situational awareness */}
{govState && (
  <VaultCard className="mb-4 border-cold-teal/20">
    <div className="flex items-start justify-between mb-3">
      <div>
        <a
          href={`/projects/${govState.project_id}`}
          className="font-heading font-semibold text-bone hover:text-cold-teal transition-colors"
        >
          {govState.name}
        </a>
        <MonoText className="text-xs mt-0.5">{govState.project_id}</MonoText>
      </div>
      <div className="flex items-center gap-2">
        {govState.current_environment && <EnvBadge env={govState.current_environment} />}
        {govState.risk_classification && (
          <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
            govState.risk_classification === "high" ? "bg-red-900/40 text-red-400" :
            govState.risk_classification === "medium" ? "bg-yellow-900/40 text-yellow-400" :
            "bg-green-900/40 text-green-400"
          }`}>
            {govState.risk_classification} risk
          </span>
        )}
      </div>
    </div>

    <div className="grid grid-cols-3 gap-3 text-xs font-mono">
      {govState.intake_card_id && (
        <div>
          <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">Intake Card</p>
          <MonoText>{govState.intake_card_id}</MonoText>
        </div>
      )}
      {govState.goal_id && (
        <div>
          <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">WTK Goal</p>
          <MonoText>{govState.goal_id}</MonoText>
        </div>
      )}
      {govState.target_id && (
        <div>
          <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">Target</p>
          <MonoText>{govState.target_type ? `${govState.target_type}:` : ""}{govState.target_id}</MonoText>
        </div>
      )}
    </div>

    {govState.agent_members && (
      <div className="mt-3 pt-3 border-t border-slate-border flex flex-wrap gap-2">
        {govState.agent_members.coordinator && (
          <span className="px-2 py-0.5 rounded border border-cold-teal/30 text-[10px] font-mono text-cold-teal">
            coord: {govState.agent_members.coordinator}
          </span>
        )}
        {govState.agent_members.workers.map((w) => (
          <span key={w} className="px-2 py-0.5 rounded border border-slate-border text-[10px] font-mono text-bone-muted">
            worker: {w}
          </span>
        ))}
        {govState.agent_members.evaluators.map((e) => (
          <span key={e} className="px-2 py-0.5 rounded border border-clinical-cyan/30 text-[10px] font-mono text-clinical-cyan">
            eval: {e}
          </span>
        ))}
      </div>
    )}

    {govState.pending_approvals_count > 1 && (
      <p className="mt-2 text-[10px] font-mono text-bone-dim">
        {govState.pending_approvals_count - 1} other pending approval{govState.pending_approvals_count > 2 ? "s" : ""} on this project
      </p>
    )}
  </VaultCard>
)}
```

- [ ] **Step 3: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|✓" | head -10
```

Expected: `✓ built in ...`

- [ ] **Step 4: Run full test suite**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/contract --ignore=tests/security
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ApprovalDetailPage.tsx
git commit -m "feat(governance): ApprovalDetailPage shows project/goal/agent context panel for reviewers"
```

---

## Self-Review

**Spec coverage:**
- ✅ ProjectRow gains `intake_card_id`, `goal_id`, `target_type`, `target_id`, `risk_classification`, `agent_members`, `litellm_key_refs`, `memory_policy_refs`, `qualification_packet_id` — Task 1–2
- ✅ `POST /projects/{id}/agents` — WTK registers coordinator/workers/evaluators — Task 4
- ✅ `GET /projects/{id}/governance-state` — returns full governance container state — Task 4
- ✅ ProjectPage "Team" tab — intent, agent team, runtime keys, inline pending approvals — Task 6
- ✅ ProjectPage Overview governance context strip — Task 7
- ✅ Dashboard governance queue — pending approvals grouped by project — Task 8
- ✅ ApprovalDetailPage project/goal/agent context panel — Task 9
- ✅ All governance fields exposed in existing `GET /projects/{id}` — Task 4

**Placeholder scan:** None found — all JSX blocks, Python routes, and SQL migrations are fully specified.

**Type consistency:** `GovernanceState` defined once in `frontend/src/api/projects.ts` and consumed in `ProjectPage.tsx`, `ApprovalDetailPage.tsx`. `agent_members` shape (`coordinator`, `workers`, `evaluators`) is consistent across Python dict and TypeScript interface. `DashboardProject.agent_members` uses the same shape.

**Boundary check:** No execution logic added. All new code is read/write of governance metadata and display. Task packets are not touched — that cleanup is a separate decision.
