# Migration Cleanup + Governance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit pending migrations 002–004, create migration 005 to replace all lifespan ALTER TABLE hacks, remove those hacks from main.py, and fix the two remaining governance antipatterns (silent gate re-eval failure and unbounded webhook registry).

**Architecture:** Four independent fixes that must land in order — schema first, then app layer cleanup, then behavioral fixes. Migration 005 is PG-only (SQLite tests use `create_all`). Gate re-eval fix changes a `pass` to a conditional re-raise or warning log based on the gate's `auto_pass` flag. Webhook fix adds a cap to the in-memory registry backed by a new config var.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL, pytest-asyncio, pydantic-settings

---

## File Map

| File | Action | Why |
|---|---|---|
| `src/pearl/db/migrations/versions/002_add_execution_phase_to_task_packets.py` | Commit existing | Already made idempotent |
| `src/pearl/db/migrations/versions/003_add_trust_accumulation_to_gates.py` | Commit existing | Already made idempotent |
| `src/pearl/db/migrations/versions/004_add_allowance_profile_versioning.py` | Commit existing | Already made idempotent |
| `src/pearl/db/migrations/versions/005_lifespan_alters_to_migration.py` | Create | Covers all 10 lifespan ALTER TABLE blocks |
| `src/pearl/main.py` | Modify (remove lines 91–138) | Remove lifespan ALTER TABLE blocks after migration 005 exists |
| `src/pearl/api/routes/task_packets.py` | Modify | Fix 3 bare `except Exception: pass` blocks |
| `src/pearl/config.py` | Modify | Add `max_webhook_subscriptions` setting |
| `src/pearl/events/webhook_config.py` | Modify | Enforce cap in `WebhookRegistry.register()` |
| `tests/test_webhooks.py` | Modify | Add cap enforcement test |

---

## Task 1: Verify and Commit Migrations 002–004

**Files:**
- No changes needed — migrations are already written and idempotent

- [ ] **Step 1: Run the full test suite to verify migrations don't break anything**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Expected: all tests pass (SQLite tests use `create_all`, not Alembic — migrations won't run, but models must be correct)

- [ ] **Step 2: Confirm the three migration files are staged**

```bash
git diff --stat HEAD -- src/pearl/db/migrations/versions/002_add_execution_phase_to_task_packets.py src/pearl/db/migrations/versions/003_add_trust_accumulation_to_gates.py src/pearl/db/migrations/versions/004_add_allowance_profile_versioning.py
```

Expected: each file shows lines added (the `_column_exists` idempotency guards)

- [ ] **Step 3: Commit migrations 002–004**

```bash
git add src/pearl/db/migrations/versions/002_add_execution_phase_to_task_packets.py \
        src/pearl/db/migrations/versions/003_add_trust_accumulation_to_gates.py \
        src/pearl/db/migrations/versions/004_add_allowance_profile_versioning.py \
        docker-compose.yaml \
        frontend/src/pages/SettingsPage.tsx
git commit -m "$(cat <<'EOF'
chore: make migrations 002-004 idempotent with column-exists guards

Adds _column_exists() to each migration upgrade() so re-running against
an already-migrated schema is safe. Also includes pending docker-compose
and SettingsPage changes from the same working set.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Write Tests for Migration 005 Behavior

We can't unit-test Alembic migrations directly in SQLite, but we can write a test that asserts the lifespan no longer contains any ALTER TABLE blocks — this will fail now (before the fix) and pass after.

**Files:**
- Create: `tests/test_lifespan_no_alter_table.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lifespan_no_alter_table.py
"""Regression test: main.py lifespan must not contain raw ALTER TABLE blocks.

Schema changes must go through Alembic migrations (CLAUDE.md antipattern).
This test reads the source file and fails if any ALTER TABLE call is present
inside the lifespan function body.
"""
import re
from pathlib import Path


def test_lifespan_has_no_alter_table():
    main_src = (Path(__file__).parent.parent / "src/pearl/main.py").read_text()

    # Find the lifespan function body (from `async def lifespan` to `yield`)
    lifespan_match = re.search(
        r"async def lifespan.*?yield",
        main_src,
        re.DOTALL,
    )
    assert lifespan_match, "Could not find lifespan function in main.py"

    lifespan_body = lifespan_match.group(0)

    alter_table_calls = re.findall(r'ALTER TABLE', lifespan_body, re.IGNORECASE)
    assert not alter_table_calls, (
        f"Found {len(alter_table_calls)} ALTER TABLE call(s) in lifespan. "
        "Schema changes must use Alembic migrations, not lifespan hacks. "
        "See CLAUDE.md antipatterns."
    )
```

- [ ] **Step 2: Run to confirm it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_lifespan_no_alter_table.py -v
```

Expected: `FAILED tests/test_lifespan_no_alter_table.py::test_lifespan_has_no_alter_table` with message about N ALTER TABLE calls found.

---

## Task 3: Create Migration 005

Migration 005 covers all 10 ALTER TABLE blocks currently in `main.py` lifespan (lines 91–138). This migration is PostgreSQL-only — `information_schema.columns` is not available in SQLite, but that's fine because SQLite tests use `Base.metadata.create_all` and never run Alembic migrations.

**Files:**
- Create: `src/pearl/db/migrations/versions/005_lifespan_alters_to_migration.py`

- [ ] **Step 1: Create the migration file**

```python
# src/pearl/db/migrations/versions/005_lifespan_alters_to_migration.py
"""Move lifespan ALTER TABLE hacks into a proper idempotent migration.

Revision ID: 005
Revises: 004
Create Date: 2026-04-18

Covers columns that were previously added via try/except ALTER TABLE blocks
in main.py lifespan. PostgreSQL only — SQLite uses create_all.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _col_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name=:t"
        ),
        {"t": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # org_baselines.bu_id
    if _table_exists("org_baselines") and not _col_exists("org_baselines", "bu_id"):
        op.add_column(
            "org_baselines",
            sa.Column("bu_id", sa.String(128), nullable=True),
        )

    # integration_endpoints.project_id — make nullable (PostgreSQL only)
    if _table_exists("integration_endpoints") and _col_exists("integration_endpoints", "project_id"):
        op.alter_column("integration_endpoints", "project_id", nullable=True)

    # projects.claude_md_verified
    if _table_exists("projects") and not _col_exists("projects", "claude_md_verified"):
        op.add_column(
            "projects",
            sa.Column(
                "claude_md_verified",
                sa.Boolean(),
                nullable=False,
                server_default="FALSE",
            ),
        )

    # exception_records enrichment columns
    _exception_cols = [
        ("exception_type", sa.String(20), "exception"),
        ("title", sa.String(256), None),
        ("risk_rating", sa.String(20), None),
        ("remediation_plan", sa.Text(), None),
        ("board_briefing", sa.Text(), None),
    ]
    if _table_exists("exception_records"):
        for col_name, col_type, default in _exception_cols:
            if not _col_exists("exception_records", col_name):
                kwargs: dict = {"nullable": True}
                if default is not None:
                    kwargs["server_default"] = default
                    kwargs["nullable"] = False
                op.add_column("exception_records", sa.Column(col_name, col_type, **kwargs))

        if not _col_exists("exception_records", "finding_ids"):
            op.add_column(
                "exception_records",
                sa.Column("finding_ids", sa.dialects.postgresql.JSONB(), nullable=True),
            )

    # projects.tags
    if _table_exists("projects") and not _col_exists("projects", "tags"):
        op.add_column(
            "projects",
            sa.Column("tags", sa.dialects.postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    if _table_exists("projects"):
        if _col_exists("projects", "tags"):
            op.drop_column("projects", "tags")
        if _col_exists("projects", "claude_md_verified"):
            op.drop_column("projects", "claude_md_verified")

    if _table_exists("exception_records"):
        for col in ("finding_ids", "board_briefing", "remediation_plan", "risk_rating", "title", "exception_type"):
            if _col_exists("exception_records", col):
                op.drop_column("exception_records", col)

    if _table_exists("integration_endpoints") and _col_exists("integration_endpoints", "project_id"):
        op.alter_column("integration_endpoints", "project_id", nullable=False)

    if _table_exists("org_baselines") and _col_exists("org_baselines", "bu_id"):
        op.drop_column("org_baselines", "bu_id")
```

- [ ] **Step 2: Run the test suite to make sure no test breaks from the new file**

```bash
PEARL_LOCAL=1 pytest tests/ -q --ignore=tests/test_lifespan_no_alter_table.py
```

Expected: all pass

---

## Task 4: Remove Lifespan ALTER TABLE Blocks from main.py

**Files:**
- Modify: `src/pearl/main.py` lines 91–138

- [ ] **Step 1: Remove the ALTER TABLE block from main.py**

In `src/pearl/main.py`, replace lines 88–139 (the entire "Safe column additions" section) with just the `create_all` call:

Old (lines 88–139):
```python
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe column additions for existing DBs (create_all skips existing tables)
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE org_baselines ADD COLUMN bu_id VARCHAR(128)"))
            else:
                await conn.execute(text("ALTER TABLE org_baselines ADD COLUMN IF NOT EXISTS bu_id VARCHAR(128) REFERENCES business_units(bu_id)"))
        except Exception:
            pass  # Column already exists
        # Allow org-level integrations (project_id nullable)
        try:
            if "sqlite" not in db_url:
                await conn.execute(text("ALTER TABLE integration_endpoints ALTER COLUMN project_id DROP NOT NULL"))
        except Exception:
            pass  # Already nullable or table doesn't exist yet
        # CLAUDE.md governance verification flag
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN claude_md_verified BOOLEAN NOT NULL DEFAULT 0"))
            else:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS claude_md_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        except Exception:
            pass  # Already exists
        # Exception governance enrichment columns
        for col_sql_sqlite, col_sql_pg in [
            ("ALTER TABLE exception_records ADD COLUMN exception_type VARCHAR(20) NOT NULL DEFAULT 'exception'",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS exception_type VARCHAR(20) NOT NULL DEFAULT 'exception'"),
            ("ALTER TABLE exception_records ADD COLUMN title VARCHAR(256)",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS title VARCHAR(256)"),
            ("ALTER TABLE exception_records ADD COLUMN risk_rating VARCHAR(20)",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(20)"),
            ("ALTER TABLE exception_records ADD COLUMN remediation_plan TEXT",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS remediation_plan TEXT"),
            ("ALTER TABLE exception_records ADD COLUMN board_briefing TEXT",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS board_briefing TEXT"),
            ("ALTER TABLE exception_records ADD COLUMN finding_ids JSON",
             "ALTER TABLE exception_records ADD COLUMN IF NOT EXISTS finding_ids JSONB"),
        ]:
            try:
                await conn.execute(text(col_sql_sqlite if "sqlite" in db_url else col_sql_pg))
            except Exception:
                pass
        # Project tags column
        try:
            if "sqlite" in db_url:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN tags JSON"))
            else:
                await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS tags JSONB"))
        except Exception:
            pass
    logger.info("DB tables created/verified (%s)", "sqlite" if "sqlite" in db_url else "postgresql")
```

New (replace with just):
```python
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB tables created/verified (%s)", "sqlite" if "sqlite" in db_url else "postgresql")
```

- [ ] **Step 2: Run full test suite — including the new regression test**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Expected: ALL tests pass, including `test_lifespan_no_alter_table.py::test_lifespan_has_no_alter_table`.

- [ ] **Step 3: Commit**

```bash
git add src/pearl/db/migrations/versions/005_lifespan_alters_to_migration.py \
        src/pearl/main.py \
        tests/test_lifespan_no_alter_table.py
git commit -m "$(cat <<'EOF'
fix: move lifespan ALTER TABLE hacks to migration 005

Raw ALTER TABLE blocks in main.py lifespan ran on every startup — a
CLAUDE.md antipattern. Migration 005 covers all 10 affected columns
idempotently. Regression test asserts no ALTER TABLE remains in lifespan.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Write Tests for Gate Re-eval Behavior

**Files:**
- Create: `tests/test_gate_reeval_behavior.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_reeval_behavior.py
"""Tests for gate re-evaluation behavior on task packet completion.

CLAUDE.md governance constraint:
- Manual gate (auto_pass=False): re-eval failure must propagate (raise)
- Auto-elevation gate (auto_pass=True): re-eval failure must log warning, not raise
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.repositories.promotion_repo import PromotionGateRepository
from pearl.services.id_generator import generate_id
from pearl.db.models.promotion import PromotionGateRow


async def _create_project(client, project_id: str) -> str:
    r = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": project_id,
            "name": f"Gate reeval test {project_id}",
            "description": "Gate re-eval behavior test",
            "owner_team": "test-team",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": False,
        },
    )
    assert r.status_code == 201, r.text
    return project_id


async def _create_and_claim_packet(db_session: AsyncSession, project_id: str) -> str:
    tp_id = generate_id("tp_")
    repo = TaskPacketRepository(db_session)
    await repo.create(
        task_packet_id=tp_id,
        project_id=project_id,
        environment="sandbox",
        trace_id=generate_id("trace_"),
        packet_data={
            "task_type": "remediate_gate_blocker",
            "task_packet_id": tp_id,
            "status": "claimed",
            "rule_id": generate_id("rule_"),
            "rule_type": "test_rule",
            "fix_guidance": "Fix it",
            "transition": "sandbox->dev",
            "created_by": "test",
        },
    )
    # Mark as claimed
    row = await repo.get(tp_id)
    row.status = "claimed"
    row.agent_id = "test-agent"
    await db_session.commit()
    return tp_id


@pytest.mark.asyncio
async def test_gate_reeval_failure_raises_in_manual_mode(client, db_session):
    """When gate.auto_pass=False and gate re-eval throws, the complete endpoint raises."""
    pid = await _create_project(client, "proj_reeval_manual")
    tp_id = await _create_and_claim_packet(db_session, pid)

    # Simulate a gate with auto_pass=False (manual mode)
    manual_gate = MagicMock(spec=PromotionGateRow)
    manual_gate.auto_pass = False

    with patch(
        "pearl.api.routes.task_packets.PromotionGateRepository"
    ) as MockRepo:
        mock_instance = AsyncMock()
        mock_instance.get_for_transition = AsyncMock(return_value=manual_gate)
        MockRepo.return_value = mock_instance

        with patch(
            "pearl.api.routes.task_packets.evaluate_promotion",
            side_effect=RuntimeError("gate evaluator exploded"),
        ):
            r = await client.post(
                f"/api/v1/task-packets/{tp_id}/complete",
                json={"status": "completed", "fix_summary": "done"},
            )

    # Manual mode: re-eval failure must surface as a server error
    assert r.status_code == 500, (
        f"Expected 500 for manual gate re-eval failure, got {r.status_code}: {r.text}"
    )


@pytest.mark.asyncio
async def test_gate_reeval_failure_logs_warning_in_auto_mode(client, db_session):
    """When gate.auto_pass=True and gate re-eval throws, the complete endpoint still returns 200."""
    pid = await _create_project(client, "proj_reeval_auto")
    tp_id = await _create_and_claim_packet(db_session, pid)

    auto_gate = MagicMock(spec=PromotionGateRow)
    auto_gate.auto_pass = True

    with patch(
        "pearl.api.routes.task_packets.PromotionGateRepository"
    ) as MockRepo:
        mock_instance = AsyncMock()
        mock_instance.get_for_transition = AsyncMock(return_value=auto_gate)
        MockRepo.return_value = mock_instance

        with patch(
            "pearl.api.routes.task_packets.evaluate_promotion",
            side_effect=RuntimeError("gate evaluator exploded"),
        ):
            with patch("pearl.api.routes.task_packets.logger") as mock_logger:
                r = await client.post(
                    f"/api/v1/task-packets/{tp_id}/complete",
                    json={"status": "completed", "fix_summary": "done"},
                )

    # Auto mode: re-eval failure must NOT fail the request
    assert r.status_code == 200, (
        f"Expected 200 for auto gate re-eval failure, got {r.status_code}: {r.text}"
    )
    # Must log a warning, not silently pass
    mock_logger.warning.assert_called_once()
```

- [ ] **Step 2: Run to confirm both tests fail**

```bash
PEARL_LOCAL=1 pytest tests/test_gate_reeval_behavior.py -v
```

Expected: both tests fail. The manual-mode test will fail because the current code returns 200 (swallows the exception). The auto-mode test may fail because `PromotionGateRepository` isn't imported in the route yet.

---

## Task 6: Fix Gate Re-eval Behavior in task_packets.py

**Files:**
- Modify: `src/pearl/api/routes/task_packets.py`

- [ ] **Step 1: Add logger and required imports at the top of task_packets.py**

Find the existing imports block at the top. Add after the existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Move transition computation out of the gate re-eval try block**

Find this block (around line 298):

```python
    # Re-evaluate gate after completion (best-effort)
    gate_status = None
    gate_evaluation_id = None
    try:
        from pearl.services.promotion.gate_evaluator import evaluate_promotion
        from pearl.api.routes.stream import publish_event

        transition = (packet.packet_data or {}).get("transition", "")
        source_env = packet.environment
        target_env = None
        if "->" in transition:
            parts = transition.split("->")
            source_env = parts[0].strip()
            target_env = parts[1].strip()

        evaluation = await evaluate_promotion(
```

Replace it with:

```python
    # Re-evaluate gate after completion
    gate_status = None
    gate_evaluation_id = None

    # Compute transition envs before the try block so they're available for gate lookup
    _transition = (packet.packet_data or {}).get("transition", "")
    _source_env = packet.environment
    _target_env: str | None = None
    if "->" in _transition:
        _parts = _transition.split("->")
        _source_env = _parts[0].strip()
        _target_env = _parts[1].strip()

    # Look up gate mode: manual gates must surface re-eval failures
    from pearl.repositories.promotion_repo import PromotionGateRepository
    _gate_repo = PromotionGateRepository(db)
    _gate = await _gate_repo.get_for_transition(_source_env, _target_env or "", packet.project_id)
    _gate_is_manual = not (_gate.auto_pass if _gate else False)

    try:
        from pearl.services.promotion.gate_evaluator import evaluate_promotion
        from pearl.api.routes.stream import publish_event

        evaluation = await evaluate_promotion(
            project_id=packet.project_id,
            source_environment=_source_env,
            target_environment=_target_env,
            session=db,
        )
```

- [ ] **Step 3: Fix the gate re-eval except clause (was line 344)**

Find:
```python
    except Exception:
        pass  # Gate re-evaluation is best-effort
```

Replace with:
```python
    except Exception:
        if _gate_is_manual:
            raise
        logger.warning(
            "Gate re-evaluation failed (auto-elevation mode, project=%s, %s->%s)",
            packet.project_id, _source_env, _target_env,
            exc_info=True,
        )
```

- [ ] **Step 4: Fix the telemetry except clause (was line 293)**

Find:
```python
    except Exception:
        pass  # Telemetry is best-effort
```

Replace with:
```python
    except Exception:
        logger.warning("Audit event creation failed for packet %s", packet_id, exc_info=True)
```

- [ ] **Step 5: Fix the auto-elevation except clause in `_check_auto_elevation` (was line 432)**

Find at the bottom of `_check_auto_elevation`:
```python
    except Exception:
        pass  # Auto-elevation is best-effort
```

Replace with:
```python
    except Exception:
        logger.warning(
            "Auto-elevation failed (project=%s, %s->%s)",
            project_id, source_env, target_env,
            exc_info=True,
        )
```

- [ ] **Step 6: Also update the reference to `source_env`/`target_env` inside the try block's SSE publish call**

Inside the gate re-eval try block, find the `publish_event` call and the `_check_auto_elevation` call, which referenced the old local variable names `source_env` and `target_env`. Update those references to use `_source_env` and `_target_env`:

Find:
```python
            await publish_event(redis, "gate_updated", {
                "project_id": packet.project_id,
                "evaluation_id": evaluation.evaluation_id,
                "gate_status": gate_status,
                "triggered_by": "task_packet_complete",
                "packet_id": packet_id,
            })

        # Auto-elevation if gate passes and transition doesn't require approval
        if evaluation.status.value == "passed" if hasattr(evaluation.status, "value") else evaluation.status == "passed":
            await _check_auto_elevation(
                project_id=packet.project_id,
                source_env=source_env,
                target_env=target_env or "",
                session=db,
                request=request,
            )
```

Replace with:
```python
            await publish_event(redis, "gate_updated", {
                "project_id": packet.project_id,
                "evaluation_id": evaluation.evaluation_id,
                "gate_status": gate_status,
                "triggered_by": "task_packet_complete",
                "packet_id": packet_id,
            })

        # Auto-elevation if gate passes and transition doesn't require approval
        if evaluation.status.value == "passed" if hasattr(evaluation.status, "value") else evaluation.status == "passed":
            await _check_auto_elevation(
                project_id=packet.project_id,
                source_env=_source_env,
                target_env=_target_env or "",
                session=db,
                request=request,
            )
```

- [ ] **Step 7: Run the gate re-eval tests**

```bash
PEARL_LOCAL=1 pytest tests/test_gate_reeval_behavior.py -v
```

Expected: both tests pass

- [ ] **Step 8: Run full suite**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add src/pearl/api/routes/task_packets.py tests/test_gate_reeval_behavior.py
git commit -m "$(cat <<'EOF'
fix: gate re-eval failure raises in manual mode, logs warning in auto mode

Bare except Exception: pass in task_packets.py silently swallowed gate
re-evaluation failures. In manual gates (auto_pass=False) this bypasses
human oversight. Now: manual mode re-raises, auto-elevation mode logs a
warning. Telemetry and auto-elevation also log instead of silently passing.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Write Test for Webhook Registry Cap

**Files:**
- Modify: `tests/test_webhooks.py`

- [ ] **Step 1: Add cap enforcement test at the bottom of test_webhooks.py**

```python
def test_webhook_registry_enforces_subscription_cap():
    """Registering beyond max_subscriptions raises ConflictError."""
    from pearl.errors.exceptions import ConflictError

    registry = WebhookRegistry(max_subscriptions=3)
    for i in range(3):
        registry.register(WebhookSubscription(url=f"http://host{i}.example.com/hook", secret="s"))

    with pytest.raises(ConflictError, match="limit"):
        registry.register(WebhookSubscription(url="http://overflow.example.com/hook", secret="s"))

    # Existing subscriptions should be unchanged
    assert len(registry.list_all()) == 3
```

- [ ] **Step 2: Run to confirm it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_webhooks.py::test_webhook_registry_enforces_subscription_cap -v
```

Expected: `FAILED` — `WebhookRegistry.__init__` doesn't accept `max_subscriptions` yet and `register()` has no cap check.

---

## Task 8: Implement Webhook Registry Cap

**Files:**
- Modify: `src/pearl/config.py`
- Modify: `src/pearl/events/webhook_config.py`

- [ ] **Step 1: Add the config setting to config.py**

Find the `rate_limit_enabled` block in `config.py`:
```python
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_writes_per_minute: int = 100
    rate_limit_reads_per_minute: int = 1000
```

Add after it:
```python
    # Webhook subscriptions
    max_webhook_subscriptions: int = 100  # PEARL_MAX_WEBHOOK_SUBSCRIPTIONS
```

- [ ] **Step 2: Update webhook_config.py**

Replace the entire `webhook_config.py` with:

```python
"""Webhook subscription management."""

from dataclasses import dataclass, field

from pearl.errors.exceptions import ConflictError


@dataclass
class WebhookSubscription:
    """A registered webhook endpoint."""

    url: str
    secret: str
    event_types: list[str] = field(default_factory=list)
    active: bool = True


class WebhookRegistry:
    """In-memory registry for webhook subscriptions.

    In production this would be backed by a database table.
    """

    def __init__(self, max_subscriptions: int = 100) -> None:
        self._subscriptions: list[WebhookSubscription] = []
        self._max_subscriptions = max_subscriptions

    def register(self, subscription: WebhookSubscription) -> None:
        if len(self._subscriptions) >= self._max_subscriptions:
            raise ConflictError(
                f"Webhook subscription limit reached ({self._max_subscriptions}). "
                "Remove an existing subscription before adding a new one."
            )
        self._subscriptions.append(subscription)

    def unregister(self, url: str) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.url != url]

    def get_subscribers(self, event_type: str) -> list[WebhookSubscription]:
        """Return active subscriptions matching the event type."""
        return [
            s
            for s in self._subscriptions
            if s.active and (not s.event_types or event_type in s.event_types)
        ]

    def list_all(self) -> list[WebhookSubscription]:
        return list(self._subscriptions)


# Module-level singleton — cap from settings
from pearl.config import settings  # noqa: E402
webhook_registry = WebhookRegistry(max_subscriptions=settings.max_webhook_subscriptions)
```

- [ ] **Step 3: Run the webhook cap test**

```bash
PEARL_LOCAL=1 pytest tests/test_webhooks.py::test_webhook_registry_enforces_subscription_cap -v
```

Expected: PASSED

- [ ] **Step 4: Run the full webhook test file**

```bash
PEARL_LOCAL=1 pytest tests/test_webhooks.py -v
```

Expected: all tests pass. (The existing tests create fresh `WebhookRegistry()` instances — they aren't affected by the singleton or cap change.)

- [ ] **Step 5: Run the full test suite**

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/pearl/config.py src/pearl/events/webhook_config.py tests/test_webhooks.py
git commit -m "$(cat <<'EOF'
fix: enforce webhook subscription cap in WebhookRegistry

Adds PEARL_MAX_WEBHOOK_SUBSCRIPTIONS config var (default 100).
WebhookRegistry.register() raises ConflictError when the cap is reached.
Addresses the unbounded in-memory list antipattern from CLAUDE.md.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Commit migrations 002–004 | Task 1 |
| Create migration 005 (lifespan ALTER TABLE) | Task 3 |
| Remove lifespan ALTER TABLE blocks | Task 4 |
| Regression test for lifespan | Task 2 |
| Gate re-eval: manual mode raises | Task 6 |
| Gate re-eval: auto mode logs warning | Task 6 |
| Telemetry: log not silent pass | Task 6 |
| Auto-elevation: log not silent pass | Task 6 |
| Webhook: cap enforced | Task 8 |
| Webhook: `PEARL_MAX_WEBHOOK_SUBSCRIPTIONS` config var | Task 8 |

**Known constraints:**
- Migration 005 `_col_exists` uses `information_schema` — PG only. SQLite tests are unaffected because they use `create_all`.
- The gate re-eval fix introduces `PromotionGateRepository` import inside the route function. If the DB query itself fails, `_gate` will be `None`, `_gate_is_manual` will be `True` (safe default — manual behavior is more conservative), and the subsequent gate re-eval failure will raise. This is the correct fail-safe.
- The `webhook_registry` singleton imports `settings` at module load time. This is already done for other singletons in the codebase.
