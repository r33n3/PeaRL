"""Shared fixtures for the attack chain eval harness.

These fixtures provide a pre-seeded test environment:
  - test_project:       a registered project in the DB
  - pending_approval:   a pending approval request for the project
  - test_findings:      a set of open findings for the project

Root conftest.py fixtures (client, reviewer_client, app, db_session) are
inherited automatically — no need to re-declare them here.

Note: operator_client is just `client` — in PEARL_LOCAL=1 mode all
unauthenticated requests get operator role. The naming is explicit to
make the test intent clear.
"""

import pytest

from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_project(session, project_id: str) -> None:
    from pearl.db.models.project import ProjectRow
    existing = await session.get(ProjectRow, project_id)
    if existing:
        return
    row = ProjectRow(
        project_id=project_id,
        name=f"Attack chain test project {project_id}",
        description="Auto-seeded for attack chain tests",
        owner_team="security-test",
        business_criticality="high",
        external_exposure="internal_only",
        ai_enabled=True,
    )
    session.add(row)
    await session.flush()


async def _seed_approval(session, approval_id: str, project_id: str) -> None:
    from pearl.db.models.approval import ApprovalRequestRow
    row = ApprovalRequestRow(
        approval_request_id=approval_id,
        project_id=project_id,
        environment="dev",
        request_type="deployment_gate",
        status="pending",
        request_data={"description": "Test approval for attack chain"},
        trace_id=generate_id("trace_"),
    )
    session.add(row)
    await session.flush()


async def _seed_finding(session, finding_id: str, project_id: str) -> None:
    from datetime import datetime, timezone
    from pearl.db.models.finding import FindingRow
    row = FindingRow(
        finding_id=finding_id,
        project_id=project_id,
        source={"tool": "sast"},
        environment="dev",
        category="injection",
        severity="high",
        title="SQL injection in login handler",
        status="open",
        full_data={"description": "Test finding"},
        detected_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_project(db_session):
    """Seed and return a project_id for use in attack chain tests."""
    project_id = generate_id("proj_")
    await _seed_project(db_session, project_id)
    await db_session.commit()
    return project_id


@pytest.fixture
async def pending_approval(db_session, test_project):
    """Seed and return a pending approval_request_id."""
    approval_id = generate_id("appr_")
    await _seed_approval(db_session, approval_id, test_project)
    await db_session.commit()
    return approval_id


@pytest.fixture
async def test_findings(db_session, test_project):
    """Seed and return a list of finding_ids."""
    ids = [generate_id("find_") for _ in range(5)]
    for fid in ids:
        await _seed_finding(db_session, fid, test_project)
    await db_session.commit()
    return ids


@pytest.fixture
def prod_app(db_engine):
    """Test app with OpenAPI schema explicitly disabled (simulates production mode).

    Used by L2 schema discovery tests to verify that /openapi.json, /docs,
    and /redoc are inaccessible when expose_openapi=False.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from pearl.main import create_app
    from pearl.config import settings

    original = settings.expose_openapi
    settings.expose_openapi = False
    try:
        _app = create_app()
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        _app.state.db_engine = db_engine
        _app.state.db_session_factory = session_factory
        _app.state.redis = None
    finally:
        settings.expose_openapi = original
    return _app


@pytest.fixture
async def prod_client(prod_app):
    """Async HTTP test client backed by a production-mode app (schema disabled)."""
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=prod_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def operator_client(client):
    """Alias for the default test client (operator role in PEARL_LOCAL mode).

    Named explicitly so test intent is clear: this is an operator-privileged
    client attempting governance actions it should be denied.
    """
    return client
