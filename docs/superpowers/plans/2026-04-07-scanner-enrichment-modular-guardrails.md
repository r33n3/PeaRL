# Scanner Enrichment + Modular Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After MASS pushes findings to PeaRL, immediately pull verdict/compliance/policies as a background task, store scanner policies in a modular table, surface them in the Guardrails tab with source badges, extend the promotion gate to use verdict risk level, and stamp auto-resolved findings with the confirming scanner.

**Architecture:** Six targeted additions to the existing system. New `scanner_policy_store` table stores per-source per-policy-type content. A FastAPI BackgroundTask fires on each MASS ingest, calling three new `MassClient` methods. The `recommended-guardrails` endpoint merges scanner policies with PeaRL-generated ones. GuardrailsTab renders a source badge per entry. The gate evaluator's AI risk check is extended to also consume `verdict.risk_level`.

**Tech Stack:** FastAPI BackgroundTasks, SQLAlchemy async, httpx, Alembic, React + TypeScript, React Query, @tanstack/react-query

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/pearl/db/models/scanner_policy.py` | `ScannerPolicyRow` SQLAlchemy model |
| Create | `src/pearl/db/migrations/versions/006_add_scanner_policy_store.py` | Alembic migration (005 is reserved for lifespan cleanup) |
| Create | `src/pearl/repositories/scanner_policy_repo.py` | `ScannerPolicyRepository` — upsert + list |
| Modify | `src/pearl/db/models/__init__.py` | Register `ScannerPolicyRow` |
| Modify | `src/pearl/scanning/mass_bridge.py` | Add `get_verdict()`, `get_compliance()`, `get_policies()` to `MassClient` |
| Modify | `src/pearl/api/routes/scanning.py` | Add BackgroundTask + `confirmed_by` to auto-resolve |
| Modify | `src/pearl/api/routes/guardrails.py` | Merge scanner policies into response |
| Modify | `src/pearl/services/promotion/gate_evaluator.py` | Add `mass_verdict_risk_level` to context + gate check |
| Modify | `frontend/src/api/guardrails.ts` | Add `source` field to `GuardrailRecommendation` |
| Modify | `frontend/src/components/pipeline/GuardrailsTab.tsx` | Render source badge per card |
| Create | `tests/test_scanner_policy_store.py` | Repo upsert + list tests |
| Create | `tests/test_mass_enrichment.py` | BackgroundTask + `confirmed_by` tests |
| Modify | `tests/test_guardrails.py` (or create) | Scanner policies appear in response |
| Modify | `tests/test_gate_evaluator.py` (or create) | Verdict risk level blocks gate |

---

## Task 1: `scanner_policy_store` table, model, and repository

**Files:**
- Create: `src/pearl/db/models/scanner_policy.py`
- Create: `src/pearl/db/migrations/versions/006_add_scanner_policy_store.py`
- Create: `src/pearl/repositories/scanner_policy_repo.py`
- Modify: `src/pearl/db/models/__init__.py`
- Test: `tests/test_scanner_policy_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scanner_policy_store.py
"""Tests for ScannerPolicyRepository."""
import pytest
from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id


async def _make_project(db_session) -> str:
    pid = generate_id("proj")
    repo = ProjectRepository(db_session)
    await repo.create(
        project_id=pid,
        name="Test Project",
        description="test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
    )
    await db_session.commit()
    return pid


@pytest.mark.asyncio
async def test_upsert_creates_new_row(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)
    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan-001",
        policy_type="cedar",
        content={"statement": "permit(principal, action, resource);"},
    )
    await db_session.commit()
    rows = await repo.list_by_project(pid)
    assert len(rows) == 1
    assert rows[0].source == "mass"
    assert rows[0].policy_type == "cedar"
    assert rows[0].scan_id == "scan-001"


@pytest.mark.asyncio
async def test_upsert_replaces_existing_row(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)
    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan-001",
        policy_type="cedar",
        content={"statement": "old"},
    )
    await db_session.commit()
    await repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan-002",
        policy_type="cedar",
        content={"statement": "new"},
    )
    await db_session.commit()
    rows = await repo.list_by_project(pid)
    assert len(rows) == 1
    assert rows[0].scan_id == "scan-002"
    assert rows[0].content["statement"] == "new"


@pytest.mark.asyncio
async def test_list_by_project_filters_by_source(db_session):
    pid = await _make_project(db_session)
    repo = ScannerPolicyRepository(db_session)
    await repo.upsert(pid, "mass", "scan-001", "cedar", {"x": 1})
    await repo.upsert(pid, "snyk", "scan-002", "nginx", {"x": 2})
    await db_session.commit()
    mass_rows = await repo.list_by_project(pid, source="mass")
    assert len(mass_rows) == 1
    assert mass_rows[0].source == "mass"
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
PEARL_LOCAL=1 pytest tests/test_scanner_policy_store.py -v
```
Expected: `ImportError: cannot import name 'ScannerPolicyRepository'`

- [ ] **Step 3: Create the model**

```python
# src/pearl/db/models/scanner_policy.py
"""ScannerPolicyStore table — stores scanner-generated policies per project per source."""

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base


class ScannerPolicyRow(Base):
    __tablename__ = "scanner_policy_store"
    __table_args__ = (
        UniqueConstraint("project_id", "source", "policy_type", name="uq_scanner_policy"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)   # "mass", "snyk", "sonarqube"
    scan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "cedar", "bedrock", etc.
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Register the model in `src/pearl/db/models/__init__.py`**

Find the imports block and add:

```python
from pearl.db.models.scanner_policy import ScannerPolicyRow  # noqa: F401
```

Add `"ScannerPolicyRow"` to the `__all__` list.

- [ ] **Step 5: Create the repository**

```python
# src/pearl/repositories/scanner_policy_repo.py
"""Repository for scanner_policy_store table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.scanner_policy import ScannerPolicyRow
from pearl.services.id_generator import generate_id


class ScannerPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        project_id: str,
        source: str,
        scan_id: str,
        policy_type: str,
        content: dict,
    ) -> ScannerPolicyRow:
        """Upsert by (project_id, source, policy_type) — one row per scanner per policy type."""
        stmt = select(ScannerPolicyRow).where(
            ScannerPolicyRow.project_id == project_id,
            ScannerPolicyRow.source == source,
            ScannerPolicyRow.policy_type == policy_type,
        ).limit(1)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if row:
            row.scan_id = scan_id
            row.content = content
            row.updated_at = now
        else:
            row = ScannerPolicyRow(
                id=generate_id("sps"),
                project_id=project_id,
                source=source,
                scan_id=scan_id,
                policy_type=policy_type,
                content=content,
                updated_at=now,
            )
            self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_project(
        self, project_id: str, source: str | None = None
    ) -> list[ScannerPolicyRow]:
        """Return all scanner policies for a project, optionally filtered by source."""
        stmt = select(ScannerPolicyRow).where(ScannerPolicyRow.project_id == project_id)
        if source:
            stmt = stmt.where(ScannerPolicyRow.source == source)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 6: Create the Alembic migration**

```python
# src/pearl/db/migrations/versions/006_add_scanner_policy_store.py
"""Add scanner_policy_store table.

Revision ID: 006
Revises: 004
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "004"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("scanner_policy_store"):
        return
    op.create_table(
        "scanner_policy_store",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), sa.ForeignKey("projects.project_id"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("scan_id", sa.String(128), nullable=False),
        sa.Column("policy_type", sa.String(50), nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "source", "policy_type", name="uq_scanner_policy"),
    )


def downgrade() -> None:
    op.drop_table("scanner_policy_store")
```

- [ ] **Step 7: Run tests — expect all 3 to pass**

```bash
PEARL_LOCAL=1 pytest tests/test_scanner_policy_store.py -v
```
Expected:
```
PASSED tests/test_scanner_policy_store.py::test_upsert_creates_new_row
PASSED tests/test_scanner_policy_store.py::test_upsert_replaces_existing_row
PASSED tests/test_scanner_policy_store.py::test_list_by_project_filters_by_source
```

- [ ] **Step 8: Commit**

```bash
git add src/pearl/db/models/scanner_policy.py \
        src/pearl/db/migrations/versions/006_add_scanner_policy_store.py \
        src/pearl/repositories/scanner_policy_repo.py \
        src/pearl/db/models/__init__.py \
        tests/test_scanner_policy_store.py
git commit -m "feat: scanner_policy_store table, model, and repository"
```

---

## Task 2: MassClient enrichment methods

**Files:**
- Modify: `src/pearl/scanning/mass_bridge.py`
- Test: `tests/test_mass_enrichment.py` (stub for now, extended in Task 3)

- [ ] **Step 1: Write failing tests for the three new methods**

```python
# tests/test_mass_enrichment.py
"""Tests for MassClient enrichment methods and mass_ingest BackgroundTask."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from pearl.scanning.mass_bridge import MassClient


@pytest.mark.asyncio
async def test_get_verdict_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "risk_level": "high",
        "summary": "Test summary",
        "key_risks": ["risk1"],
        "immediate_actions": ["action1"],
        "confidence": 0.9,
        "finding_counts": {"total": 1, "high": 1},
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result["risk_level"] == "high"
    assert result["confidence"] == 0.9


@pytest.mark.asyncio
async def test_get_compliance_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "frameworks": {"owasp_llm": {"passed": True, "score": 1.0}},
        "overall_passed": True,
        "failed_controls": [],
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_compliance("scan-123")
    assert result["overall_passed"] is True


@pytest.mark.asyncio
async def test_get_policies_returns_list():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [
        {"policy_type": "cedar", "content": {"statement": "permit(...);"} },
        {"policy_type": "bedrock", "content": {"topicPolicyConfig": {}}},
    ]
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_policies("scan-123")
    assert len(result) == 2
    assert result[0]["policy_type"] == "cedar"


@pytest.mark.asyncio
async def test_get_verdict_returns_empty_dict_on_404():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result == {}
```

- [ ] **Step 2: Run tests — expect AttributeError (methods don't exist yet)**

```bash
PEARL_LOCAL=1 pytest tests/test_mass_enrichment.py::test_get_verdict_returns_dict -v
```
Expected: `AttributeError: 'MassClient' object has no attribute 'get_verdict'`

- [ ] **Step 3: Add the three methods to `MassClient` in `src/pearl/scanning/mass_bridge.py`**

Find the end of the `MassClient` class (after `wait_for_completion`) and add:

```python
    async def get_verdict(self, scan_id: str) -> dict:
        """GET /scans/{scan_id}/verdict — returns verdict dict or {} on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/verdict",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS verdict fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return {}
        except Exception as exc:
            logger.warning("MASS verdict fetch error scan_id=%s: %s", scan_id, exc)
            return {}

    async def get_compliance(self, scan_id: str) -> dict:
        """GET /scans/{scan_id}/compliance — returns compliance dict or {} on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/compliance",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS compliance fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return {}
        except Exception as exc:
            logger.warning("MASS compliance fetch error scan_id=%s: %s", scan_id, exc)
            return {}

    async def get_policies(self, scan_id: str) -> list[dict]:
        """GET /scans/{scan_id}/policies — returns list of {policy_type, content} or [] on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/policies",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            # Accept list or dict keyed by policy_type
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [{"policy_type": k, "content": v} for k, v in data.items()]
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS policies fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return []
        except Exception as exc:
            logger.warning("MASS policies fetch error scan_id=%s: %s", scan_id, exc)
            return []
```

- [ ] **Step 4: Run tests — expect all 4 to pass**

```bash
PEARL_LOCAL=1 pytest tests/test_mass_enrichment.py -v
```
Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/scanning/mass_bridge.py tests/test_mass_enrichment.py
git commit -m "feat: MassClient get_verdict/get_compliance/get_policies methods"
```

---

## Task 3: BackgroundTask enrichment + `confirmed_by` on auto-resolve

**Files:**
- Modify: `src/pearl/api/routes/scanning.py`
- Test: `tests/test_mass_enrichment.py` (extend with integration tests)

- [ ] **Step 1: Add integration tests for the BackgroundTask and confirmed_by**

Append to `tests/test_mass_enrichment.py`:

```python
from unittest.mock import patch, AsyncMock
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
from pearl.services.id_generator import generate_id


async def _make_project(db_session) -> str:
    pid = generate_id("proj")
    repo = ProjectRepository(db_session)
    await repo.create(
        project_id=pid,
        name="Test Project",
        description="test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
    )
    await db_session.commit()
    return pid


@pytest.mark.asyncio
async def test_mass_ingest_stamps_confirmed_by_on_resolve(client, db_session):
    """Re-scan auto-resolve stamps confirmed_by on the finding."""
    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from sqlalchemy import select

    pid = await _make_project(db_session)
    find_repo = FindingRepository(db_session)

    # Create an existing open MASS finding
    ext_id = f"mass-scan-old-find-001"
    await find_repo.create(
        finding_id=generate_id("find_"),
        project_id=pid,
        environment="dev",
        category="security",
        severity="high",
        title="Old finding",
        source={"tool_name": "mass2", "system": "mass_scan", "external_id": ext_id},
        full_data={"finding_id": "find-001"},
        normalized=True,
        detected_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        batch_id=None,
        status="open",
        schema_version="1.1",
    )
    await db_session.commit()

    # Ingest a new scan that does NOT include the old finding → should auto-resolve it
    payload = {
        "scan_id": "scan-new",
        "risk_score": 2.0,
        "categories_completed": ["jailbreak"],
        "findings": [],  # old finding absent → resolved
    }
    resp = await client.post(f"/api/v1/projects/{pid}/integrations/mass/ingest", json=payload)
    assert resp.status_code == 200
    assert resp.json()["findings_resolved"] == 1

    # Verify confirmed_by stamped
    stmt = select(FindingRow).where(FindingRow.project_id == pid, FindingRow.source["external_id"].as_string() == ext_id)
    result = await db_session.execute(stmt)
    finding = result.scalar_one()
    assert finding.status == "resolved"
    assert finding.full_data.get("confirmed_by") == "mass2"
    assert finding.full_data.get("confirmed_scan_id") == "scan-new"
```

- [ ] **Step 2: Run test — expect failure (confirmed_by not stamped yet)**

```bash
PEARL_LOCAL=1 pytest tests/test_mass_enrichment.py::test_mass_ingest_stamps_confirmed_by_on_resolve -v
```
Expected: `AssertionError: assert None == 'mass2'`

- [ ] **Step 3: Add `confirmed_by` to the auto-resolve loop in `scanning.py`**

Find the auto-resolve loop (around line 556):

```python
    # Auto-resolve open mass2 findings not in current scan
    resolved = 0
    for f in existing_mass:
        ext_id = (f.source or {}).get("external_id", "")
        if f.status == "open" and ext_id not in current_ext_ids:
            f.status = "resolved"
            f.resolved_at = datetime.now(timezone.utc)
            await db.flush()
            resolved += 1
```

Replace with:

```python
    # Auto-resolve open mass2 findings not in current scan
    resolved = 0
    for f in existing_mass:
        ext_id = (f.source or {}).get("external_id", "")
        if f.status == "open" and ext_id not in current_ext_ids:
            f.status = "resolved"
            f.resolved_at = datetime.now(timezone.utc)
            f.full_data = {
                **(f.full_data or {}),
                "confirmed_by": "mass2",
                "confirmed_scan_id": body.scan_id,
            }
            await db.flush()
            resolved += 1
```

- [ ] **Step 4: Run the confirmed_by test — expect pass**

```bash
PEARL_LOCAL=1 pytest tests/test_mass_enrichment.py::test_mass_ingest_stamps_confirmed_by_on_resolve -v
```
Expected: PASS

- [ ] **Step 5: Add the BackgroundTask function and wire it into `mass_ingest`**

At the top of `scanning.py`, add to the imports:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Request
```

(Replace the existing `from fastapi import APIRouter, Depends` if present — check what's already imported and add only `BackgroundTasks` and `Request`.)

Add the enrichment task function just before the `mass_ingest` route definition (around line 470):

```python
async def _enrich_from_mass(project_id: str, scan_id: str, session_factory) -> None:
    """BackgroundTask: pull verdict, compliance, and policies from MASS after ingest."""
    from pearl.scanning.mass_bridge import MassClient
    from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    mass_url = settings.mass_url
    mass_api_key = settings.mass_api_key
    if not mass_url or not mass_api_key:
        return  # MASS not configured — skip silently

    client = MassClient(base_url=mass_url, api_key=mass_api_key)

    # Pull all three in parallel
    import asyncio
    verdict, compliance, policies = await asyncio.gather(
        client.get_verdict(scan_id),
        client.get_compliance(scan_id),
        client.get_policies(scan_id),
        return_exceptions=True,
    )

    # Normalise exceptions to empty defaults
    verdict = verdict if isinstance(verdict, dict) else {}
    compliance = compliance if isinstance(compliance, dict) else {}
    policies = policies if isinstance(policies, list) else []

    async with session_factory() as session:
        from sqlalchemy import select
        from pearl.db.models.finding import FindingRow
        from datetime import datetime, timezone

        # Update mass2_marker with verdict + compliance
        marker_ext_id = f"mass-marker-{project_id}"
        stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["external_id"].as_string() == marker_ext_id,
        ).limit(1)
        result = await session.execute(stmt)
        marker = result.scalar_one_or_none()
        if marker:
            marker.full_data = {
                **(marker.full_data or {}),
                "verdict": verdict,
                "compliance": compliance,
                "has_agent_trace": bool(verdict),  # proxy: if verdict exists, trace was captured
            }
            await session.flush()

        # Upsert scanner policies
        if policies:
            policy_repo = ScannerPolicyRepository(session)
            for policy in policies:
                policy_type = policy.get("policy_type", "")
                content = policy.get("content", policy)
                if policy_type:
                    await policy_repo.upsert(
                        project_id=project_id,
                        source="mass",
                        scan_id=scan_id,
                        policy_type=policy_type,
                        content=content if isinstance(content, dict) else {"raw": content},
                    )

        await session.commit()
```

Update the `mass_ingest` function signature to add `BackgroundTasks` and `Request`:

```python
@router.post("/projects/{project_id}/integrations/mass/ingest", status_code=200)
async def mass_ingest(
    project_id: str,
    body: MassIngestRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
```

Add the background task call just before `return` at the end of `mass_ingest` (after `await db.commit()`):

```python
    # Fire enrichment in background — pull verdict, compliance, policies from MASS
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None:
        background_tasks.add_task(
            _enrich_from_mass,
            project_id=project_id,
            scan_id=body.scan_id,
            session_factory=session_factory,
        )

    return {
        "project_id": project_id,
        ...
    }
```

- [ ] **Step 6: Run full enrichment test suite**

```bash
PEARL_LOCAL=1 pytest tests/test_mass_enrichment.py -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/pearl/api/routes/scanning.py tests/test_mass_enrichment.py
git commit -m "feat: MASS enrichment BackgroundTask + confirmed_by on auto-resolve"
```

---

## Task 4: Extend `recommended-guardrails` to merge scanner policies

**Files:**
- Modify: `src/pearl/api/routes/guardrails.py`
- Test: `tests/test_guardrails_scanner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_guardrails_scanner.py
"""Tests for scanner policy entries in recommended-guardrails response."""
import pytest
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
from pearl.services.id_generator import generate_id


async def _make_project(db_session) -> str:
    pid = generate_id("proj")
    repo = ProjectRepository(db_session)
    await repo.create(
        project_id=pid,
        name="Test Project",
        description="test",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
    )
    await db_session.commit()
    return pid


@pytest.mark.asyncio
async def test_recommended_guardrails_includes_scanner_policies(client, db_session):
    """Scanner policies from scanner_policy_store appear in recommended-guardrails response."""
    pid = await _make_project(db_session)

    # Seed a MASS policy
    policy_repo = ScannerPolicyRepository(db_session)
    await policy_repo.upsert(
        project_id=pid,
        source="mass",
        scan_id="scan-001",
        policy_type="cedar",
        content={"statement": "permit(principal, action, resource);"},
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{pid}/recommended-guardrails")
    assert resp.status_code == 200
    data = resp.json()

    scanner_entries = [g for g in data["recommended_guardrails"] if g.get("source") == "mass"]
    assert len(scanner_entries) == 1
    entry = scanner_entries[0]
    assert entry["policy_type"] == "cedar"
    assert entry["source"] == "mass"
    assert "content" in entry


@pytest.mark.asyncio
async def test_pearl_generated_guardrails_have_pearl_source(client, db_session):
    """PeaRL-generated guardrails have source='pearl'."""
    pid = await _make_project(db_session)

    resp = await client.get(f"/api/v1/projects/{pid}/recommended-guardrails")
    assert resp.status_code == 200
    data = resp.json()

    for g in data["recommended_guardrails"]:
        assert "source" in g, f"guardrail {g.get('id')} missing source field"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
PEARL_LOCAL=1 pytest tests/test_guardrails_scanner.py -v
```
Expected: `AssertionError` on missing `source` field.

- [ ] **Step 3: Extend `get_recommended_guardrails` in `src/pearl/api/routes/guardrails.py`**

At the top of the function after the import block inside the function, add the scanner policy import:

```python
    from pearl.repositories.scanner_policy_repo import ScannerPolicyRepository
```

After the `guardrail_entries` list is built (after the `for g in recommended:` loop), append scanner policy entries:

```python
    # Add source="pearl" to PeaRL-generated entries
    for entry in guardrail_entries:
        entry["source"] = "pearl"

    # Merge scanner-sourced policies from scanner_policy_store
    policy_repo = ScannerPolicyRepository(db)
    scanner_policies = await policy_repo.list_by_project(project_id)
    for sp in scanner_policies:
        guardrail_entries.append({
            "id": f"{sp.source}-{sp.policy_type}-{project_id}",
            "name": f"{sp.policy_type.replace('_', ' ').title()} Policy — {sp.source.upper()}",
            "source": sp.source,
            "policy_type": sp.policy_type,
            "content": sp.content,
            "description": f"Generated by {sp.source.upper()} scan {sp.scan_id}",
            "category": "access_control",
            "severity": "high",
            "implementation_steps": [
                f"Deploy this {sp.policy_type} policy from the {sp.source.upper()} scan."
            ],
        })
```

- [ ] **Step 4: Run tests — expect pass**

```bash
PEARL_LOCAL=1 pytest tests/test_guardrails_scanner.py -v
```
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/pearl/api/routes/guardrails.py tests/test_guardrails_scanner.py
git commit -m "feat: recommended-guardrails merges scanner policies with source attribution"
```

---

## Task 5: GuardrailsTab source badge (frontend)

**Files:**
- Modify: `frontend/src/api/guardrails.ts`
- Modify: `frontend/src/components/pipeline/GuardrailsTab.tsx`

- [ ] **Step 1: Add `source`, `policy_type`, `content` to `GuardrailRecommendation` in `guardrails.ts`**

Find the `GuardrailRecommendation` interface and add three optional fields:

```typescript
export interface GuardrailRecommendation {
  id: string;
  name: string;
  description: string;
  category: string;
  severity: string;
  implementation_steps: string[];
  code_examples?: Record<string, string>;
  bedrock_config?: BedrockConfig;
  cedar_policy?: CedarPolicy;
  source?: string;        // "pearl" | "mass" | "snyk" | "sonarqube"
  policy_type?: string;   // "cedar" | "bedrock" | "litellm" | "nginx" | "nemo"
  content?: unknown;      // raw policy content from scanner
}
```

- [ ] **Step 2: Add `SourceBadge` component and render it in `GuardrailCard`**

In `frontend/src/components/pipeline/GuardrailsTab.tsx`, add the `SourceBadge` component after the `PlatformTag` component (around line 54):

```tsx
function SourceBadge({ source }: { source?: string }) {
  if (!source || source === "pearl") return null;
  const label =
    source === "mass" ? "MASS 2.0" :
    source === "snyk" ? "Snyk" :
    source === "sonarqube" ? "SonarQube" :
    source.toUpperCase();
  return (
    <span className="text-[10px] font-mono px-2 py-0.5 rounded border bg-cyan-500/10 text-cyan-300 border-cyan-500/20">
      {label}
    </span>
  );
}
```

In `GuardrailCard`, add the badge to the name row (the `div` with `flex items-center gap-2 mb-2`):

```tsx
function GuardrailCard({ rec }: { rec: GuardrailRecommendation }) {
  const [stepsOpen, setStepsOpen] = useState(false);
  const hasPlatformConfig = !!(rec.bedrock_config || rec.cedar_policy);

  return (
    <VaultCard>
      {/* Name row */}
      <div className="flex items-center gap-2 mb-2">
        <SeverityDot severity={rec.severity} />
        <span className="text-sm font-heading text-white font-semibold">{rec.name}</span>
        <SourceBadge source={rec.source} />
        <span className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-white/50 border border-white/10">
          {rec.category}
        </span>
      </div>
      {/* ... rest unchanged ... */}
```

- [ ] **Step 3: For scanner-sourced entries, render `content` in a CodeBlock when no bedrock/cedar config**

In `GuardrailCard`, after the `hasPlatformConfig` check, add a scanner content block:

```tsx
      {/* Scanner policy content (when no bedrock/cedar config) */}
      {!hasPlatformConfig && rec.content && (
        <CodeBlock>
          {typeof rec.content === "string"
            ? rec.content
            : JSON.stringify(rec.content, null, 2)}
        </CodeBlock>
      )}
```

Place this before the collapsible implementation steps block.

- [ ] **Step 4: Type-check**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL/frontend && npx tsc --noEmit 2>&1 | grep -E "GuardrailsTab|guardrails|SourceBadge" || echo "No TS errors"
```

Expected: `No TS errors`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/guardrails.ts frontend/src/components/pipeline/GuardrailsTab.tsx
git commit -m "feat: GuardrailsTab source badge for scanner-identified policies"
```

---

## Task 6: Gate evaluator — verdict risk level check

**Files:**
- Modify: `src/pearl/services/promotion/gate_evaluator.py`
- Test: `tests/test_gate_verdict.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gate_verdict.py
"""Tests for verdict.risk_level in AI_RISK_ACCEPTABLE gate evaluation."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_ctx(mass_scan_seen=True, risk_score=2.0, verdict_risk_level=None):
    """Build a minimal _EvalContext for gate evaluation tests."""
    from pearl.services.promotion.gate_evaluator import _EvalContext
    ctx = _EvalContext()
    ctx.mass_scan_seen = mass_scan_seen
    ctx.mass_risk_score = risk_score
    ctx.mass_verdict_risk_level = verdict_risk_level
    ctx.open_findings = []
    ctx.mass_scan_completed = mass_scan_seen
    return ctx


def _make_rule(threshold=7.0):
    rule = MagicMock()
    rule.threshold = threshold
    return rule


def test_high_verdict_blocks_even_with_acceptable_score():
    """risk_level='high' blocks the gate even when numeric risk_score is low."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level="high")
    rule = _make_rule(threshold=7.0)
    passed, message, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert not passed
    assert "high" in message.lower()


def test_critical_verdict_blocks():
    """risk_level='critical' blocks the gate."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=1.0, verdict_risk_level="critical")
    rule = _make_rule()
    passed, message, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert not passed


def test_low_verdict_passes_with_acceptable_score():
    """risk_level='low' + acceptable score → passes."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level="low")
    rule = _make_rule()
    passed, _, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert passed


def test_missing_verdict_falls_back_to_score():
    """No verdict → existing numeric risk_score logic applies."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level=None)
    rule = _make_rule()
    passed, _, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert passed
```

- [ ] **Step 2: Run tests — expect AttributeError**

```bash
PEARL_LOCAL=1 pytest tests/test_gate_verdict.py -v
```
Expected: `AttributeError: '_EvalContext' object has no attribute 'mass_verdict_risk_level'`

- [ ] **Step 3: Add `mass_verdict_risk_level` to `_EvalContext`**

Find the MASS 2.0 context block in `_EvalContext.__init__` (around line 312):

```python
        # MASS 2.0 context
        self.mass_scan_seen: bool = False
        self.mass_risk_score: float = 0.0
```

Replace with:

```python
        # MASS 2.0 context
        self.mass_scan_seen: bool = False
        self.mass_risk_score: float = 0.0
        self.mass_verdict_risk_level: str | None = None  # "low"|"medium"|"high"|"critical"
```

- [ ] **Step 4: Load `mass_verdict_risk_level` in `_build_eval_context`**

Find the block that sets `ctx.mass_risk_score` (around line 517):

```python
    ctx.mass_scan_seen = mass_marker is not None
    if mass_marker:
        ctx.mass_risk_score = float((mass_marker.full_data or {}).get("risk_score", 0.0))
```

Replace with:

```python
    ctx.mass_scan_seen = mass_marker is not None
    if mass_marker:
        ctx.mass_risk_score = float((mass_marker.full_data or {}).get("risk_score", 0.0))
        verdict = (mass_marker.full_data or {}).get("verdict", {})
        ctx.mass_verdict_risk_level = verdict.get("risk_level") if isinstance(verdict, dict) else None
```

- [ ] **Step 5: Update `_eval_ai_risk_acceptable` to check verdict first**

Find the function (around line 964):

```python
def _eval_ai_risk_acceptable(rule, ctx):
    threshold = rule.threshold or 7.0
    # Check MASS 2.0 risk score if a scan was ingested
    if ctx.mass_scan_seen:
        if ctx.mass_risk_score <= threshold:
            return True, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} is within threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
        return False, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} exceeds threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
```

Replace with:

```python
_BLOCKING_RISK_LEVELS = {"critical", "high"}

def _eval_ai_risk_acceptable(rule, ctx):
    threshold = rule.threshold or 7.0
    if ctx.mass_scan_seen:
        # Verdict risk_level takes precedence over numeric score when present
        if ctx.mass_verdict_risk_level in _BLOCKING_RISK_LEVELS:
            return (
                False,
                f"MASS 2.0 verdict risk level '{ctx.mass_verdict_risk_level}' exceeds acceptable threshold",
                {"verdict_risk_level": ctx.mass_verdict_risk_level, "threshold": threshold},
            )
        if ctx.mass_risk_score <= threshold:
            return True, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} is within threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
        return False, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} exceeds threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
```

- [ ] **Step 6: Run tests — expect all 4 to pass**

```bash
PEARL_LOCAL=1 pytest tests/test_gate_verdict.py -v
```
Expected: all 4 pass.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/contract --ignore=tests/e2e 2>&1 | tail -15
```
Expected: all passing, no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/pearl/services/promotion/gate_evaluator.py tests/test_gate_verdict.py
git commit -m "feat: gate evaluator checks verdict.risk_level before numeric risk_score"
```

---

## Self-Review

After all tasks are committed, run:

```bash
PEARL_LOCAL=1 pytest tests/test_scanner_policy_store.py tests/test_mass_enrichment.py tests/test_guardrails_scanner.py tests/test_gate_verdict.py -v
```

Expected: all tests green.

Spec coverage check:
- ✅ Enrichment pullback — Task 3 (`_enrich_from_mass` BackgroundTask)
- ✅ `scanner_policy_store` table — Task 1
- ✅ `recommended-guardrails` merges scanner policies — Task 4
- ✅ GuardrailsTab source badge — Task 5
- ✅ `confirmed_by` on auto-resolve — Task 3
- ✅ Gate reads `verdict.risk_level` — Task 6
- ✅ Modular pattern — `source` column + `ScannerPolicyRepository.upsert()` work for any scanner
