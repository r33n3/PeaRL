"""Slack interactive message handler — receives button clicks from Slack approval notifications."""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.config import settings
from pearl.repositories.approval_repo import ApprovalRequestRepository, ApprovalDecisionRepository
from pearl.repositories.approval_comment_repo import ApprovalCommentRepository
from pearl.events.governance_events import emit_governance_event, APPROVAL_DECIDED, APPROVAL_NEEDS_INFO
from pearl.services.id_generator import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Slack"])


async def _verify_slack_signature(request: Request) -> bytes:
    """Verify the Slack request signature.

    Slack signs requests using HMAC-SHA256 with the signing secret.
    See: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    body = await request.body()

    signing_secret = getattr(settings, "slack_signing_secret", None)
    if not signing_secret:
        logger.warning("Slack signing secret not configured, skipping verification")
        return body

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    # Reject requests older than 5 minutes to prevent replay attacks
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=403, detail="Request timestamp too old")
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid timestamp")

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    return body


@router.post("/webhooks/slack/interactions")
async def handle_slack_interaction(request: Request) -> dict:
    """Handle Slack interactive message payloads (button clicks).

    Slack sends a URL-encoded payload with a JSON string in the `payload` field.
    Action IDs follow the pattern: approve_{approval_id}, reject_{approval_id},
    request_info_{approval_id}
    """
    body = await _verify_slack_signature(request)

    # Parse the URL-encoded body
    parsed = parse_qs(body.decode("utf-8"))
    payload_str = parsed.get("payload", [None])[0]
    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload JSON")

    # Extract action and user info
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}  # No action to process

    action = actions[0]
    action_id = action.get("action_id", "")
    slack_user = payload.get("user", {})
    slack_username = slack_user.get("username", slack_user.get("name", "slack-user"))

    # Parse action: approve_{id}, reject_{id}, request_info_{id}
    if action_id.startswith("approve_"):
        approval_id = action_id[len("approve_"):]
        return await _handle_approve(approval_id, slack_username, payload)
    elif action_id.startswith("reject_"):
        approval_id = action_id[len("reject_"):]
        return await _handle_reject(approval_id, slack_username, payload)
    elif action_id.startswith("request_info_"):
        approval_id = action_id[len("request_info_"):]
        return await _handle_request_info(approval_id, slack_username, payload)
    elif action_id.startswith("view_"):
        # View in Dashboard — just acknowledge
        return {"ok": True}

    logger.warning("Unknown Slack action: %s", action_id)
    return {"ok": True}


async def _handle_approve(approval_id: str, username: str, payload: dict) -> dict:
    """Process an approval from Slack."""
    from pearl.main import app

    async with app.state.db_session_factory() as db:
        req_repo = ApprovalRequestRepository(db)
        approval = await req_repo.get(approval_id)

        if not approval:
            return _slack_response("Approval request not found.", ephemeral=True)

        if approval.status not in ("pending", "needs_info"):
            return _slack_response(
                f"This request has already been *{approval.status}*.",
                ephemeral=True,
            )

        # Update approval status
        approval.status = "approved"
        approval.request_data = {**approval.request_data, "status": "approved"}

        # Create decision record
        dec_repo = ApprovalDecisionRepository(db)
        await dec_repo.create(
            approval_request_id=approval_id,
            decision="approve",
            decided_by=f"slack:{username}",
            decider_role="security_lead",
            reason=f"Approved via Slack by @{username}",
            conditions=None,
            decided_at=None,
            trace_id=None,
        )

        await db.commit()

        # Emit governance event
        await emit_governance_event(
            APPROVAL_DECIDED,
            {
                "approval_request_id": approval_id,
                "project_id": approval.project_id,
                "decision": "approve",
                "decided_by": f"slack:{username}",
            },
            db_session=db,
        )
        await db.commit()

    return _slack_update(
        f":white_check_mark: *Approved* by @{username}",
        approval_id,
    )


async def _handle_reject(approval_id: str, username: str, payload: dict) -> dict:
    """Process a rejection from Slack."""
    from pearl.main import app

    async with app.state.db_session_factory() as db:
        req_repo = ApprovalRequestRepository(db)
        approval = await req_repo.get(approval_id)

        if not approval:
            return _slack_response("Approval request not found.", ephemeral=True)

        if approval.status not in ("pending", "needs_info"):
            return _slack_response(
                f"This request has already been *{approval.status}*.",
                ephemeral=True,
            )

        # Update approval status
        approval.status = "rejected"
        approval.request_data = {**approval.request_data, "status": "rejected"}

        # Create decision record
        dec_repo = ApprovalDecisionRepository(db)
        await dec_repo.create(
            approval_request_id=approval_id,
            decision="reject",
            decided_by=f"slack:{username}",
            decider_role="security_lead",
            reason=f"Rejected via Slack by @{username}",
            conditions=None,
            decided_at=None,
            trace_id=None,
        )

        await db.commit()

        # Emit governance event
        await emit_governance_event(
            APPROVAL_DECIDED,
            {
                "approval_request_id": approval_id,
                "project_id": approval.project_id,
                "decision": "reject",
                "decided_by": f"slack:{username}",
            },
            db_session=db,
        )
        await db.commit()

    return _slack_update(
        f":x: *Rejected* by @{username}",
        approval_id,
    )


async def _handle_request_info(approval_id: str, username: str, payload: dict) -> dict:
    """Request more information from Slack."""
    from pearl.main import app

    async with app.state.db_session_factory() as db:
        req_repo = ApprovalRequestRepository(db)
        approval = await req_repo.get(approval_id)

        if not approval:
            return _slack_response("Approval request not found.", ephemeral=True)

        if approval.status not in ("pending", "needs_info"):
            return _slack_response(
                f"This request has already been *{approval.status}*.",
                ephemeral=True,
            )

        # Set status to needs_info
        approval.status = "needs_info"

        # Add comment
        comment_repo = ApprovalCommentRepository(db)
        await comment_repo.create(
            comment_id=generate_id("acmt_"),
            approval_request_id=approval_id,
            author=f"slack:{username}",
            author_role="security_lead",
            content=f"More information requested via Slack by @{username}",
            comment_type="question",
            attachments=None,
        )

        await db.commit()

        # Emit governance event
        await emit_governance_event(
            APPROVAL_NEEDS_INFO,
            {
                "approval_request_id": approval_id,
                "project_id": approval.project_id,
                "requested_by": f"slack:{username}",
            },
            db_session=db,
        )
        await db.commit()

    return _slack_update(
        f":question: *More info requested* by @{username}",
        approval_id,
    )


def _slack_response(text: str, ephemeral: bool = False) -> dict:
    """Build a Slack response payload."""
    response: dict = {"text": text}
    if ephemeral:
        response["response_type"] = "ephemeral"
    return response


def _slack_update(status_text: str, approval_id: str) -> dict:
    """Build a Slack message update that replaces the original message with the outcome."""
    return {
        "response_type": "in_channel",
        "replace_original": True,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": status_text,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Approval ID: `{approval_id}`",
                    },
                ],
            },
        ],
    }
