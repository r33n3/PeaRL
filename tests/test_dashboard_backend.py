"""Comprehensive tests for dashboard, approval comments, notifications,
governance events, and auto-approval features.

Covers:
- ApprovalCommentRow model creation and timestamp mixin
- NotificationRow model creation and defaults
- POST/GET /api/v1/approvals/{id}/comments (comment CRUD, needs_info flow)
- GET /api/v1/approvals/pending (pending + needs_info filtering)
- GET /api/v1/projects, /projects/{id} (dashboard portfolio views)
- Notification read/unread via repository
- GovernanceEvent emission and notification record creation
- Promotion gate approval_mode default and update endpoint
- ApprovalCommentRepository chronological ordering
- NotificationRepository filtering (unread, by-project, mark-read)
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.approval_comment import ApprovalCommentRow
from pearl.db.models.notification import NotificationRow
from pearl.db.models.promotion import PromotionGateRow
from pearl.events.governance_events import (
    APPROVAL_CREATED,
    APPROVAL_DECIDED,
    APPROVAL_NEEDS_INFO,
    COST_THRESHOLD_REACHED,
    EVENT_SEVERITY,
    EVENT_TITLES,
    FINDING_CRITICAL_DETECTED,
    PROMOTION_COMPLETED,
    _build_notification_body,
    _build_notification_link,
    emit_governance_event,
)
from pearl.repositories.approval_comment_repo import ApprovalCommentRepository
from pearl.repositories.notification_repo import NotificationRepository
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _unique(prefix: str = "") -> str:
    """Return a short unique suffix for test data isolation."""
    global _counter
    _counter += 1
    return f"{prefix}{int(time.time() * 1000)}_{_counter}"


def _project_payload(project_id: str | None = None) -> dict:
    """Build a minimal valid project creation payload."""
    pid = project_id or f"proj_{_unique()}"
    return {
        "schema_version": "1.1",
        "project_id": pid,
        "name": f"Test Project {pid}",
        "description": "Auto-generated for testing",
        "owner_team": "test-team",
        "business_criticality": "moderate",
        "external_exposure": "internal_only",
        "ai_enabled": False,
    }


def _approval_payload(
    approval_request_id: str | None = None,
    project_id: str = "proj_placeholder",
) -> dict:
    """Build a minimal valid approval request payload."""
    appr_id = approval_request_id or f"appr_{_unique()}"
    return {
        "schema_version": "1.1",
        "approval_request_id": appr_id,
        "project_id": project_id,
        "environment": "dev",
        "request_type": "deployment_gate",
        "trigger": "ci-pipeline",
        "requested_by": "test-user",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": f"trc_{_unique()}",
    }


def _comment_payload(
    content: str = "Test comment",
    comment_type: str = "note",
    set_needs_info: bool = False,
) -> dict:
    """Build a valid approval comment creation payload."""
    return {
        "author": "reviewer@example.com",
        "author_role": "security_lead",
        "content": content,
        "comment_type": comment_type,
        "set_needs_info": set_needs_info,
    }


async def _create_project(client, project_id: str | None = None) -> dict:
    """Helper: create a project and return its response body."""
    payload = _project_payload(project_id)
    r = await client.post("/api/v1/projects", json=payload)
    assert r.status_code == 201, f"Project creation failed: {r.text}"
    return r.json()


async def _create_approval(client, project_id: str, approval_id: str | None = None) -> dict:
    """Helper: create an approval request and return its response body."""
    payload = _approval_payload(approval_id, project_id)
    r = await client.post("/api/v1/approvals/requests", json=payload)
    assert r.status_code == 201, f"Approval creation failed: {r.text}"
    return r.json()


# =========================================================================
# 1. ApprovalCommentRow model tests
# =========================================================================


class TestApprovalCommentModel:
    """Tests for the ApprovalCommentRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_comment_row_all_fields(self, db_session: AsyncSession):
        """Creating an ApprovalCommentRow persists all expected fields."""
        # Need a project and approval first (FK constraints)
        from pearl.db.models.project import ProjectRow
        from pearl.db.models.approval import ApprovalRequestRow

        project = ProjectRow(
            project_id="proj_comment_model_test",
            name="Comment Model Test",
            owner_team="qa",
            business_criticality="moderate",
            external_exposure="internal_only",
            ai_enabled=False,
        )
        db_session.add(project)
        await db_session.flush()

        approval = ApprovalRequestRow(
            approval_request_id="appr_comment_model_001",
            project_id="proj_comment_model_test",
            environment="dev",
            request_type="deployment_gate",
            status="pending",
            request_data={"test": True},
            trace_id="trc_comment_model",
        )
        db_session.add(approval)
        await db_session.flush()

        comment = ApprovalCommentRow(
            comment_id="acmt_model_001",
            approval_request_id="appr_comment_model_001",
            author="alice@example.com",
            author_role="security_lead",
            content="Please provide more details about the network change.",
            comment_type="question",
            attachments={"files": ["evidence.pdf"]},
        )
        db_session.add(comment)
        await db_session.flush()

        assert comment.comment_id == "acmt_model_001"
        assert comment.approval_request_id == "appr_comment_model_001"
        assert comment.author == "alice@example.com"
        assert comment.author_role == "security_lead"
        assert comment.content == "Please provide more details about the network change."
        assert comment.comment_type == "question"
        assert comment.attachments == {"files": ["evidence.pdf"]}

    @pytest.mark.asyncio
    async def test_timestamp_mixin_sets_created_at(self, db_session: AsyncSession):
        """TimestampMixin should populate created_at and updated_at."""
        from pearl.db.models.project import ProjectRow
        from pearl.db.models.approval import ApprovalRequestRow

        project = ProjectRow(
            project_id="proj_ts_test",
            name="Timestamp Test",
            owner_team="qa",
            business_criticality="low",
            external_exposure="internal_only",
            ai_enabled=False,
        )
        db_session.add(project)
        await db_session.flush()

        approval = ApprovalRequestRow(
            approval_request_id="appr_ts_test_001",
            project_id="proj_ts_test",
            environment="dev",
            request_type="deployment_gate",
            status="pending",
            request_data={},
            trace_id="trc_ts_test",
        )
        db_session.add(approval)
        await db_session.flush()

        comment = ApprovalCommentRow(
            comment_id="acmt_ts_001",
            approval_request_id="appr_ts_test_001",
            author="bob@example.com",
            author_role="developer",
            content="Timestamp test comment.",
            comment_type="note",
        )
        db_session.add(comment)
        await db_session.flush()

        assert comment.created_at is not None
        assert comment.updated_at is not None
        assert isinstance(comment.created_at, datetime)
        assert isinstance(comment.updated_at, datetime)


# =========================================================================
# 2. NotificationRow model tests
# =========================================================================


class TestNotificationModel:
    """Tests for the NotificationRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_notification_all_fields(self, db_session: AsyncSession):
        """Creating a NotificationRow persists all expected fields."""
        from pearl.db.models.project import ProjectRow

        project = ProjectRow(
            project_id="proj_notif_model",
            name="Notif Model Test",
            owner_team="qa",
            business_criticality="high",
            external_exposure="customer_facing",
            ai_enabled=True,
        )
        db_session.add(project)
        await db_session.flush()

        notif = NotificationRow(
            notification_id="notif_model_001",
            recipient="all",
            project_id="proj_notif_model",
            event_type="approval.created",
            title="New approval request",
            body="Approval request created for project proj_notif_model",
            severity="info",
            read=False,
            link="/approvals/appr_123",
            extra_data={"approval_request_id": "appr_123"},
        )
        db_session.add(notif)
        await db_session.flush()

        assert notif.notification_id == "notif_model_001"
        assert notif.recipient == "all"
        assert notif.project_id == "proj_notif_model"
        assert notif.event_type == "approval.created"
        assert notif.title == "New approval request"
        assert notif.body == "Approval request created for project proj_notif_model"
        assert notif.severity == "info"
        assert notif.read is False
        assert notif.link == "/approvals/appr_123"
        assert notif.extra_data == {"approval_request_id": "appr_123"}

    @pytest.mark.asyncio
    async def test_notification_default_values(self, db_session: AsyncSession):
        """read defaults to False, severity defaults to 'info'."""
        notif = NotificationRow(
            notification_id="notif_defaults_001",
            recipient="all",
            event_type="test.event",
            title="Default test",
            body="Testing defaults",
            severity="info",
            read=False,
        )
        db_session.add(notif)
        await db_session.flush()

        assert notif.read is False
        assert notif.severity == "info"
        assert notif.link is None
        assert notif.extra_data is None
        assert notif.project_id is None

    @pytest.mark.asyncio
    async def test_notification_timestamp_mixin(self, db_session: AsyncSession):
        """Notification should get created_at/updated_at from TimestampMixin."""
        notif = NotificationRow(
            notification_id="notif_ts_001",
            recipient="admin",
            event_type="test.timestamps",
            title="Timestamp check",
            body="Verifying timestamps",
            severity="warning",
            read=False,
        )
        db_session.add(notif)
        await db_session.flush()

        assert notif.created_at is not None
        assert notif.updated_at is not None


# =========================================================================
# 3. Approval Comments API tests
# =========================================================================


class TestApprovalCommentsAPI:
    """Tests for POST/GET /api/v1/approvals/{id}/comments endpoints."""

    @pytest.mark.asyncio
    async def test_post_comment_creates_comment(self, client):
        """POST /api/v1/approvals/{id}/comments creates a comment and returns its ID."""
        proj = await _create_project(client)
        appr = await _create_approval(client, proj["project_id"])
        appr_id = appr["approval_request_id"]

        r = await client.post(
            f"/api/v1/approvals/{appr_id}/comments",
            json=_comment_payload("This looks good so far."),
        )
        assert r.status_code == 201
        body = r.json()
        assert "comment_id" in body
        assert body["comment_id"].startswith("acmt_")
        assert body["approval_request_id"] == appr_id
        assert body["author"] == "reviewer@example.com"
        assert body["comment_type"] == "note"

    @pytest.mark.asyncio
    async def test_post_comment_with_needs_info_changes_status(self, client):
        """POST with set_needs_info=True changes approval status to needs_info."""
        proj = await _create_project(client)
        appr = await _create_approval(client, proj["project_id"])
        appr_id = appr["approval_request_id"]

        r = await client.post(
            f"/api/v1/approvals/{appr_id}/comments",
            json=_comment_payload(
                "Need more evidence for the network boundary change.",
                comment_type="question",
                set_needs_info=True,
            ),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status_changed"] is True

        # Verify the approval now appears as needs_info
        r = await client.get("/api/v1/approvals/pending")
        assert r.status_code == 200
        pending = r.json()
        matching = [a for a in pending if a["approval_request_id"] == appr_id]
        assert len(matching) == 1
        assert matching[0]["status"] == "needs_info"

    @pytest.mark.asyncio
    async def test_get_comments_returns_chronological_thread(self, client):
        """GET /api/v1/approvals/{id}/comments returns comments in creation order."""
        proj = await _create_project(client)
        appr = await _create_approval(client, proj["project_id"])
        appr_id = appr["approval_request_id"]

        # Post multiple comments
        messages = [
            "First question: what is the scope?",
            "Second: evidence attached.",
            "Third: follow-up note.",
        ]
        for msg in messages:
            r = await client.post(
                f"/api/v1/approvals/{appr_id}/comments",
                json=_comment_payload(msg),
            )
            assert r.status_code == 201

        r = await client.get(f"/api/v1/approvals/{appr_id}/comments")
        assert r.status_code == 200
        thread = r.json()
        assert len(thread) == 3
        # Verify chronological order by content sequence
        assert thread[0]["content"] == messages[0]
        assert thread[1]["content"] == messages[1]
        assert thread[2]["content"] == messages[2]
        # Each comment should have a created_at timestamp
        for c in thread:
            assert "created_at" in c
            assert c["created_at"] is not None

    @pytest.mark.asyncio
    async def test_post_comment_nonexistent_approval_returns_404(self, client):
        """POST to a non-existent approval should return 404."""
        r = await client.post(
            "/api/v1/approvals/appr_does_not_exist/comments",
            json=_comment_payload("Comment on nothing."),
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_comments_nonexistent_approval_returns_404(self, client):
        """GET comments for non-existent approval should return 404."""
        r = await client.get("/api/v1/approvals/appr_nonexistent_thread/comments")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_pending_returns_pending_and_needs_info(self, client):
        """GET /api/v1/approvals/pending includes both pending and needs_info approvals."""
        proj = await _create_project(client)
        pid = proj["project_id"]

        # Create a pending approval
        appr_pending = await _create_approval(client, pid)

        # Create a second approval and mark it as needs_info
        appr_needs = await _create_approval(client, pid)
        appr_needs_id = appr_needs["approval_request_id"]
        await client.post(
            f"/api/v1/approvals/{appr_needs_id}/comments",
            json=_comment_payload("Need info", set_needs_info=True),
        )

        r = await client.get("/api/v1/approvals/pending")
        assert r.status_code == 200
        pending = r.json()
        ids = [a["approval_request_id"] for a in pending]
        assert appr_pending["approval_request_id"] in ids
        assert appr_needs_id in ids

        statuses = {a["approval_request_id"]: a["status"] for a in pending}
        assert statuses[appr_pending["approval_request_id"]] == "pending"
        assert statuses[appr_needs_id] == "needs_info"

    @pytest.mark.asyncio
    async def test_post_comment_with_evidence_type(self, client):
        """POST comment with comment_type=evidence stores correctly."""
        proj = await _create_project(client)
        appr = await _create_approval(client, proj["project_id"])
        appr_id = appr["approval_request_id"]

        r = await client.post(
            f"/api/v1/approvals/{appr_id}/comments",
            json={
                "author": "dev@example.com",
                "author_role": "developer",
                "content": "Here is the scan report showing no critical findings.",
                "comment_type": "evidence",
                "attachments": {"report_url": "s3://pearl/scans/report-123.pdf"},
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["comment_type"] == "evidence"

        # Verify it shows up in the thread
        r = await client.get(f"/api/v1/approvals/{appr_id}/comments")
        thread = r.json()
        assert len(thread) == 1
        assert thread[0]["comment_type"] == "evidence"
        assert thread[0]["attachments"] == {"report_url": "s3://pearl/scans/report-123.pdf"}


# =========================================================================
# 4. Dashboard API tests (using existing project/approval endpoints)
# =========================================================================


class TestDashboardAPI:
    """Tests for dashboard-related data access via existing API endpoints."""

    @pytest.mark.asyncio
    async def test_get_projects_returns_portfolio(self, client):
        """GET /api/v1/projects/{id} confirms project data is retrievable."""
        proj = await _create_project(client)
        pid = proj["project_id"]

        r = await client.get(f"/api/v1/projects/{pid}")
        assert r.status_code == 200
        body = r.json()
        assert body["project_id"] == pid
        assert body["name"] == proj["name"]
        assert "created_at" in body
        assert "business_criticality" in body

    @pytest.mark.asyncio
    async def test_get_project_overview_returns_details(self, client):
        """GET /api/v1/projects/{id} returns full project details for dashboard."""
        proj = await _create_project(client)
        pid = proj["project_id"]

        r = await client.get(f"/api/v1/projects/{pid}")
        assert r.status_code == 200
        body = r.json()
        assert body["project_id"] == pid
        assert body["owner_team"] == "test-team"
        assert body["external_exposure"] == "internal_only"
        assert body["ai_enabled"] is False
        assert "schema_version" in body

    @pytest.mark.asyncio
    async def test_get_pending_approvals_for_dashboard(self, client):
        """GET /api/v1/approvals/pending returns data suitable for dashboard display."""
        proj = await _create_project(client)
        pid = proj["project_id"]
        appr = await _create_approval(client, pid)

        r = await client.get("/api/v1/approvals/pending")
        assert r.status_code == 200
        pending = r.json()
        assert isinstance(pending, list)
        assert len(pending) >= 1

        # Check shape of each entry
        entry = next(a for a in pending if a["approval_request_id"] == appr["approval_request_id"])
        assert "project_id" in entry
        assert "environment" in entry
        assert "request_type" in entry
        assert "status" in entry
        assert "created_at" in entry

    @pytest.mark.asyncio
    async def test_get_approval_thread_for_dashboard(self, client):
        """GET /api/v1/approvals/{id}/comments returns full thread for dashboard view."""
        proj = await _create_project(client)
        appr = await _create_approval(client, proj["project_id"])
        appr_id = appr["approval_request_id"]

        # Simulate a conversation thread
        await client.post(
            f"/api/v1/approvals/{appr_id}/comments",
            json=_comment_payload("Reviewing the deployment gate.", "note"),
        )
        await client.post(
            f"/api/v1/approvals/{appr_id}/comments",
            json=_comment_payload("What is the rollback plan?", "question"),
        )

        r = await client.get(f"/api/v1/approvals/{appr_id}/comments")
        assert r.status_code == 200
        thread = r.json()
        assert len(thread) == 2
        assert all("author" in c for c in thread)
        assert all("author_role" in c for c in thread)
        assert all("content" in c for c in thread)
        assert all("comment_type" in c for c in thread)
        assert all("created_at" in c for c in thread)

    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(self, client):
        """GET /api/v1/projects/{nonexistent} returns 404 for dashboard."""
        r = await client.get("/api/v1/projects/proj_dashboard_nonexistent")
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_multiple_projects_portfolio(self, client):
        """Creating multiple projects and retrieving each independently."""
        pids = []
        for i in range(3):
            proj = await _create_project(client)
            pids.append(proj["project_id"])

        for pid in pids:
            r = await client.get(f"/api/v1/projects/{pid}")
            assert r.status_code == 200
            assert r.json()["project_id"] == pid


# =========================================================================
# 5. Governance Events tests
# =========================================================================


class TestGovernanceEvents:
    """Tests for governance event emission and notification creation."""

    def test_event_severity_mapping(self):
        """EVENT_SEVERITY should map event types to correct severity levels."""
        assert EVENT_SEVERITY[APPROVAL_CREATED] == "info"
        assert EVENT_SEVERITY[APPROVAL_DECIDED] == "info"
        assert EVENT_SEVERITY[APPROVAL_NEEDS_INFO] == "warning"
        assert EVENT_SEVERITY[FINDING_CRITICAL_DETECTED] == "critical"
        assert EVENT_SEVERITY[COST_THRESHOLD_REACHED] == "warning"
        assert EVENT_SEVERITY[PROMOTION_COMPLETED] == "info"

    def test_event_titles_defined(self):
        """EVENT_TITLES should have human-readable titles for all events."""
        assert EVENT_TITLES[APPROVAL_CREATED] == "New approval request"
        assert EVENT_TITLES[APPROVAL_DECIDED] == "Approval decision made"
        assert EVENT_TITLES[APPROVAL_NEEDS_INFO] == "More information requested"
        assert EVENT_TITLES[PROMOTION_COMPLETED] == "Environment promoted"
        assert EVENT_TITLES[FINDING_CRITICAL_DETECTED] == "Critical finding detected"
        assert EVENT_TITLES[COST_THRESHOLD_REACHED] == "Cost threshold reached"

    def test_notification_body_approval_created(self):
        """_build_notification_body produces correct body for approval.created."""
        body = _build_notification_body(
            APPROVAL_CREATED,
            {"project_id": "proj_acme", "request_type": "deployment_gate"},
        )
        assert "proj_acme" in body
        assert "deployment_gate" in body

    def test_notification_body_approval_decided(self):
        """_build_notification_body produces correct body for approval.decided."""
        body = _build_notification_body(
            APPROVAL_DECIDED,
            {"project_id": "proj_acme", "decision": "approve"},
        )
        assert "proj_acme" in body
        assert "approve" in body

    def test_notification_body_promotion_completed(self):
        """_build_notification_body produces correct body for promotion.completed."""
        body = _build_notification_body(
            PROMOTION_COMPLETED,
            {"project_id": "proj_acme", "source_environment": "dev", "target_environment": "pilot"},
        )
        assert "proj_acme" in body
        assert "dev" in body
        assert "pilot" in body

    def test_notification_body_finding_critical(self):
        """_build_notification_body produces correct body for critical findings."""
        body = _build_notification_body(
            FINDING_CRITICAL_DETECTED,
            {"project_id": "proj_acme", "count": 3},
        )
        assert "proj_acme" in body
        assert "3" in body
        assert "critical" in body.lower()

    def test_notification_body_needs_info(self):
        """_build_notification_body produces correct body for needs_info."""
        body = _build_notification_body(
            APPROVAL_NEEDS_INFO,
            {"project_id": "proj_acme"},
        )
        assert "proj_acme" in body
        assert "more information" in body.lower()

    def test_notification_body_cost_threshold(self):
        """_build_notification_body produces correct body for cost threshold."""
        body = _build_notification_body(
            COST_THRESHOLD_REACHED,
            {"project_id": "proj_acme"},
        )
        assert "proj_acme" in body
        assert "cost" in body.lower()

    def test_notification_body_unknown_event(self):
        """_build_notification_body falls back for unknown event types."""
        body = _build_notification_body("custom.event", {"project_id": "proj_x"})
        assert "custom.event" in body

    def test_notification_link_approval_events(self):
        """_build_notification_link creates deep link for approval events."""
        link = _build_notification_link(
            APPROVAL_CREATED,
            {"project_id": "proj_acme", "approval_request_id": "appr_123"},
        )
        assert link == "/approvals/appr_123"

        link = _build_notification_link(
            APPROVAL_DECIDED,
            {"project_id": "proj_acme", "approval_request_id": "appr_456"},
        )
        assert link == "/approvals/appr_456"

    def test_notification_link_promotion_completed(self):
        """_build_notification_link creates deep link for promotions."""
        link = _build_notification_link(
            PROMOTION_COMPLETED,
            {"project_id": "proj_acme"},
        )
        assert link == "/projects/proj_acme/promotions"

    def test_notification_link_critical_finding(self):
        """_build_notification_link creates deep link for critical findings."""
        link = _build_notification_link(
            FINDING_CRITICAL_DETECTED,
            {"project_id": "proj_acme"},
        )
        assert link == "/projects/proj_acme/findings"

    def test_notification_link_no_approval_id_returns_none(self):
        """_build_notification_link returns None when approval_request_id is missing."""
        link = _build_notification_link(
            APPROVAL_CREATED,
            {"project_id": "proj_acme"},
        )
        assert link is None

    def test_notification_link_unknown_event_returns_none(self):
        """_build_notification_link returns None for unknown event types."""
        link = _build_notification_link(
            "custom.event",
            {"project_id": "proj_acme"},
        )
        assert link is None

    @pytest.mark.asyncio
    async def test_emit_governance_event_creates_notification(self, db_session: AsyncSession):
        """emit_governance_event with a db_session creates a NotificationRow."""
        # Need a project for the FK
        from pearl.db.models.project import ProjectRow

        project = ProjectRow(
            project_id="proj_govevt_test",
            name="Governance Event Test",
            owner_team="qa",
            business_criticality="high",
            external_exposure="customer_facing",
            ai_enabled=False,
        )
        db_session.add(project)
        await db_session.flush()

        with patch("pearl.events.governance_events.emit_event", new_callable=AsyncMock, return_value=[]):
            result = await emit_governance_event(
                APPROVAL_CREATED,
                {"project_id": "proj_govevt_test", "request_type": "deployment_gate", "approval_request_id": "appr_evt_001"},
                db_session=db_session,
            )

        assert result["event_id"].startswith("gevt_")
        assert result["event_type"] == APPROVAL_CREATED
        assert result["notification_id"] is not None
        assert result["notification_id"].startswith("notif_")

        # Verify the notification is actually in the database
        repo = NotificationRepository(db_session)
        notif = await repo.get(result["notification_id"])
        assert notif is not None
        assert notif.event_type == APPROVAL_CREATED
        assert notif.project_id == "proj_govevt_test"
        assert notif.severity == "info"
        assert notif.read is False

    @pytest.mark.asyncio
    async def test_emit_governance_event_without_db_session(self):
        """emit_governance_event without db_session skips notification creation."""
        with patch("pearl.events.governance_events.emit_event", new_callable=AsyncMock, return_value=[]):
            result = await emit_governance_event(
                FINDING_CRITICAL_DETECTED,
                {"project_id": "proj_no_db", "count": 5},
                db_session=None,
            )

        assert result["event_id"].startswith("gevt_")
        assert result["notification_id"] is None

    @pytest.mark.asyncio
    async def test_emit_governance_event_severity_critical(self, db_session: AsyncSession):
        """emit_governance_event for critical finding creates notification with critical severity."""
        from pearl.db.models.project import ProjectRow

        project = ProjectRow(
            project_id="proj_crit_sev",
            name="Critical Severity Test",
            owner_team="qa",
            business_criticality="critical",
            external_exposure="public",
            ai_enabled=False,
        )
        db_session.add(project)
        await db_session.flush()

        with patch("pearl.events.governance_events.emit_event", new_callable=AsyncMock, return_value=[]):
            result = await emit_governance_event(
                FINDING_CRITICAL_DETECTED,
                {"project_id": "proj_crit_sev", "count": 2},
                db_session=db_session,
            )

        repo = NotificationRepository(db_session)
        notif = await repo.get(result["notification_id"])
        assert notif.severity == "critical"
        assert notif.title == "Critical finding detected"


# =========================================================================
# 6. Auto-Approval tests
# =========================================================================


class TestAutoApproval:
    """Tests for promotion gate approval_mode and auto-approval endpoint."""

    @pytest.mark.asyncio
    async def test_promotion_gate_default_approval_mode(self, db_session: AsyncSession):
        """PromotionGateRow.approval_mode defaults to 'manual'."""
        gate = PromotionGateRow(
            gate_id="gate_default_mode_test",
            source_environment="dev",
            target_environment="pilot",
            rules=[{"rule_type": "critical_findings_zero"}],
        )
        db_session.add(gate)
        await db_session.flush()

        assert gate.approval_mode == "manual"

    @pytest.mark.asyncio
    async def test_promotion_gate_set_auto_approval_mode(self, db_session: AsyncSession):
        """PromotionGateRow can be set to 'auto' approval mode."""
        gate = PromotionGateRow(
            gate_id="gate_auto_mode_test",
            source_environment="dev",
            target_environment="pilot",
            rules=[],
            approval_mode="auto",
        )
        db_session.add(gate)
        await db_session.flush()

        assert gate.approval_mode == "auto"

    @pytest.mark.asyncio
    async def test_update_gate_approval_mode_endpoint(self, client):
        """POST /api/v1/promotions/gates/{id}/approval-mode updates the mode."""
        # Create a gate first
        gate_id = f"gate_{_unique()}"
        r = await client.post(
            "/api/v1/promotions/gates",
            json={
                "gate_id": gate_id,
                "source_environment": "dev",
                "target_environment": "pilot",
                "rules": [],
            },
        )
        assert r.status_code == 201

        # Update to auto
        r = await client.post(
            f"/api/v1/promotions/gates/{gate_id}/approval-mode",
            json={"approval_mode": "auto"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["gate_id"] == gate_id
        assert body["approval_mode"] == "auto"

    @pytest.mark.asyncio
    async def test_update_gate_approval_mode_back_to_manual(self, client):
        """POST /api/v1/promotions/gates/{id}/approval-mode can revert to manual."""
        gate_id = f"gate_{_unique()}"
        await client.post(
            "/api/v1/promotions/gates",
            json={
                "gate_id": gate_id,
                "source_environment": "pilot",
                "target_environment": "preprod",
                "rules": [],
            },
        )

        # Set to auto
        r = await client.post(
            f"/api/v1/promotions/gates/{gate_id}/approval-mode",
            json={"approval_mode": "auto"},
        )
        assert r.status_code == 200
        assert r.json()["approval_mode"] == "auto"

        # Revert to manual
        r = await client.post(
            f"/api/v1/promotions/gates/{gate_id}/approval-mode",
            json={"approval_mode": "manual"},
        )
        assert r.status_code == 200
        assert r.json()["approval_mode"] == "manual"

    @pytest.mark.asyncio
    async def test_update_nonexistent_gate_returns_404(self, client):
        """POST approval-mode on non-existent gate returns 404."""
        r = await client.post(
            "/api/v1/promotions/gates/gate_does_not_exist/approval-mode",
            json={"approval_mode": "auto"},
        )
        assert r.status_code == 404


# =========================================================================
# 7. ApprovalCommentRepository tests
# =========================================================================


class TestApprovalCommentRepository:
    """Tests for ApprovalCommentRepository methods."""

    async def _setup_approval(self, db_session: AsyncSession, suffix: str) -> str:
        """Create a project and approval, returning the approval_request_id."""
        from pearl.db.models.project import ProjectRow
        from pearl.db.models.approval import ApprovalRequestRow

        project = ProjectRow(
            project_id=f"proj_repo_{suffix}",
            name=f"Repo Test {suffix}",
            owner_team="qa",
            business_criticality="moderate",
            external_exposure="internal_only",
            ai_enabled=False,
        )
        db_session.add(project)
        await db_session.flush()

        appr_id = f"appr_repo_{suffix}"
        approval = ApprovalRequestRow(
            approval_request_id=appr_id,
            project_id=f"proj_repo_{suffix}",
            environment="dev",
            request_type="deployment_gate",
            status="pending",
            request_data={},
            trace_id=f"trc_repo_{suffix}",
        )
        db_session.add(approval)
        await db_session.flush()
        return appr_id

    @pytest.mark.asyncio
    async def test_list_by_approval_chronological_order(self, db_session: AsyncSession):
        """list_by_approval returns comments sorted by created_at ascending."""
        appr_id = await self._setup_approval(db_session, "chrono")
        repo = ApprovalCommentRepository(db_session)

        # Create comments in order
        for i in range(3):
            await repo.create(
                comment_id=f"acmt_chrono_{i}",
                approval_request_id=appr_id,
                author=f"user{i}@example.com",
                author_role="developer",
                content=f"Comment number {i}",
                comment_type="note",
            )

        comments = await repo.list_by_approval(appr_id)
        assert len(comments) == 3
        assert comments[0].comment_id == "acmt_chrono_0"
        assert comments[1].comment_id == "acmt_chrono_1"
        assert comments[2].comment_id == "acmt_chrono_2"
        # Verify ascending order
        for j in range(len(comments) - 1):
            assert comments[j].created_at <= comments[j + 1].created_at

    @pytest.mark.asyncio
    async def test_list_by_approval_empty(self, db_session: AsyncSession):
        """list_by_approval returns empty list when no comments exist."""
        appr_id = await self._setup_approval(db_session, "empty")
        repo = ApprovalCommentRepository(db_session)
        comments = await repo.list_by_approval(appr_id)
        assert comments == []

    @pytest.mark.asyncio
    async def test_get_returns_single_comment(self, db_session: AsyncSession):
        """get() returns a single comment by ID."""
        appr_id = await self._setup_approval(db_session, "single")
        repo = ApprovalCommentRepository(db_session)

        await repo.create(
            comment_id="acmt_single_001",
            approval_request_id=appr_id,
            author="admin@example.com",
            author_role="security_lead",
            content="Single comment test.",
            comment_type="decision_note",
        )

        comment = await repo.get("acmt_single_001")
        assert comment is not None
        assert comment.comment_id == "acmt_single_001"
        assert comment.author == "admin@example.com"
        assert comment.content == "Single comment test."
        assert comment.comment_type == "decision_note"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, db_session: AsyncSession):
        """get() returns None for a non-existent comment ID."""
        repo = ApprovalCommentRepository(db_session)
        result = await repo.get("acmt_does_not_exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_approval_different_approvals_isolated(self, db_session: AsyncSession):
        """Comments from different approvals are not mixed."""
        appr_id_a = await self._setup_approval(db_session, "iso_a")
        appr_id_b = await self._setup_approval(db_session, "iso_b")
        repo = ApprovalCommentRepository(db_session)

        await repo.create(
            comment_id="acmt_iso_a1",
            approval_request_id=appr_id_a,
            author="a@example.com",
            author_role="developer",
            content="Comment for approval A",
            comment_type="note",
        )
        await repo.create(
            comment_id="acmt_iso_b1",
            approval_request_id=appr_id_b,
            author="b@example.com",
            author_role="developer",
            content="Comment for approval B",
            comment_type="note",
        )

        comments_a = await repo.list_by_approval(appr_id_a)
        comments_b = await repo.list_by_approval(appr_id_b)

        assert len(comments_a) == 1
        assert len(comments_b) == 1
        assert comments_a[0].comment_id == "acmt_iso_a1"
        assert comments_b[0].comment_id == "acmt_iso_b1"


# =========================================================================
# 8. NotificationRepository tests
# =========================================================================


class TestNotificationRepository:
    """Tests for NotificationRepository methods."""

    async def _create_notification(
        self,
        db_session: AsyncSession,
        notification_id: str,
        recipient: str = "all",
        project_id: str | None = None,
        read: bool = False,
        event_type: str = "test.event",
        severity: str = "info",
    ) -> NotificationRow:
        """Helper to insert a notification row."""
        repo = NotificationRepository(db_session)
        row = await repo.create(
            notification_id=notification_id,
            recipient=recipient,
            project_id=project_id,
            event_type=event_type,
            title=f"Test: {notification_id}",
            body=f"Body for {notification_id}",
            severity=severity,
            read=read,
        )
        return row

    @pytest.mark.asyncio
    async def test_list_unread_returns_only_unread(self, db_session: AsyncSession):
        """list_unread returns only notifications where read=False."""
        await self._create_notification(db_session, "notif_unread_1", read=False)
        await self._create_notification(db_session, "notif_unread_2", read=False)
        await self._create_notification(db_session, "notif_read_1", read=True)

        repo = NotificationRepository(db_session)
        unread = await repo.list_unread(recipient="all")
        unread_ids = [n.notification_id for n in unread]

        assert "notif_unread_1" in unread_ids
        assert "notif_unread_2" in unread_ids
        assert "notif_read_1" not in unread_ids

    @pytest.mark.asyncio
    async def test_list_unread_filters_by_recipient(self, db_session: AsyncSession):
        """list_unread returns notifications matching recipient or 'all'."""
        await self._create_notification(db_session, "notif_admin_1", recipient="admin")
        await self._create_notification(db_session, "notif_all_1", recipient="all")
        await self._create_notification(db_session, "notif_dev_1", recipient="developer")

        repo = NotificationRepository(db_session)

        # Querying for "admin" should get admin + all
        admin_unread = await repo.list_unread(recipient="admin")
        admin_ids = [n.notification_id for n in admin_unread]
        assert "notif_admin_1" in admin_ids
        assert "notif_all_1" in admin_ids
        assert "notif_dev_1" not in admin_ids

    @pytest.mark.asyncio
    async def test_mark_read_sets_read_true(self, db_session: AsyncSession):
        """mark_read updates the notification to read=True."""
        await self._create_notification(db_session, "notif_to_read", read=False)

        repo = NotificationRepository(db_session)

        # Verify it starts unread
        notif = await repo.get("notif_to_read")
        assert notif.read is False

        # Mark it read
        success = await repo.mark_read("notif_to_read")
        assert success is True

        # Flush and verify
        await db_session.flush()

        # Should no longer appear in unread list
        unread = await repo.list_unread(recipient="all")
        unread_ids = [n.notification_id for n in unread]
        assert "notif_to_read" not in unread_ids

    @pytest.mark.asyncio
    async def test_mark_read_nonexistent_returns_false(self, db_session: AsyncSession):
        """mark_read returns False for a non-existent notification."""
        repo = NotificationRepository(db_session)
        result = await repo.mark_read("notif_nonexistent_mark")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_by_project_filters_correctly(self, db_session: AsyncSession):
        """list_by_project returns only notifications for the given project."""
        from pearl.db.models.project import ProjectRow

        for pid in ["proj_notif_a", "proj_notif_b"]:
            project = ProjectRow(
                project_id=pid,
                name=f"Project {pid}",
                owner_team="qa",
                business_criticality="moderate",
                external_exposure="internal_only",
                ai_enabled=False,
            )
            db_session.add(project)
        await db_session.flush()

        await self._create_notification(db_session, "notif_projA_1", project_id="proj_notif_a")
        await self._create_notification(db_session, "notif_projA_2", project_id="proj_notif_a")
        await self._create_notification(db_session, "notif_projB_1", project_id="proj_notif_b")
        await self._create_notification(db_session, "notif_no_proj", project_id=None)

        repo = NotificationRepository(db_session)

        proj_a_notifs = await repo.list_by_project("proj_notif_a")
        proj_a_ids = [n.notification_id for n in proj_a_notifs]
        assert "notif_projA_1" in proj_a_ids
        assert "notif_projA_2" in proj_a_ids
        assert "notif_projB_1" not in proj_a_ids
        assert "notif_no_proj" not in proj_a_ids

        proj_b_notifs = await repo.list_by_project("proj_notif_b")
        proj_b_ids = [n.notification_id for n in proj_b_notifs]
        assert len(proj_b_ids) == 1
        assert "notif_projB_1" in proj_b_ids

    @pytest.mark.asyncio
    async def test_list_by_project_empty(self, db_session: AsyncSession):
        """list_by_project returns empty list for project with no notifications."""
        repo = NotificationRepository(db_session)
        result = await repo.list_by_project("proj_zero_notifications")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_unread_respects_limit(self, db_session: AsyncSession):
        """list_unread respects the limit parameter."""
        for i in range(5):
            await self._create_notification(db_session, f"notif_limit_{i}", read=False)

        repo = NotificationRepository(db_session)
        limited = await repo.list_unread(recipient="all", limit=3)
        assert len(limited) == 3

    @pytest.mark.asyncio
    async def test_list_unread_ordered_by_created_at_desc(self, db_session: AsyncSession):
        """list_unread returns newest notifications first."""
        for i in range(3):
            await self._create_notification(db_session, f"notif_order_{i}", read=False)

        repo = NotificationRepository(db_session)
        results = await repo.list_unread(recipient="all")

        # Verify descending order
        for j in range(len(results) - 1):
            assert results[j].created_at >= results[j + 1].created_at

    @pytest.mark.asyncio
    async def test_get_returns_single_notification(self, db_session: AsyncSession):
        """get() returns a single notification by ID."""
        await self._create_notification(
            db_session, "notif_get_single", severity="warning", event_type="approval.decided"
        )

        repo = NotificationRepository(db_session)
        notif = await repo.get("notif_get_single")
        assert notif is not None
        assert notif.notification_id == "notif_get_single"
        assert notif.severity == "warning"
        assert notif.event_type == "approval.decided"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, db_session: AsyncSession):
        """get() returns None for non-existent notification ID."""
        repo = NotificationRepository(db_session)
        result = await repo.get("notif_ghost")
        assert result is None
