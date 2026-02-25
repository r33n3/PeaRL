"""File-based approval flow for pearl-dev.

Requests are written to .pearl/approvals/appr_{id}.json.
Decisions are written to .pearl/approvals/appr_{id}.decision.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pearl.services.id_generator import generate_id


class ApprovalManager:
    """Manages file-based approval requests and decisions."""

    def __init__(self, approvals_dir: Path) -> None:
        self._dir = approvals_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def approvals_dir(self) -> Path:
        return self._dir

    def request_approval(
        self,
        action: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an approval request file. Returns the request data including approval_id."""
        approval_id = generate_id("appr_")
        request_data = {
            "approval_id": approval_id,
            "action": action,
            "reason": reason,
            "context": context or {},
            "status": "pending",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }

        request_path = self._dir / f"{approval_id}.json"
        request_path.write_text(
            json.dumps(request_data, indent=2), encoding="utf-8"
        )
        return request_data

    def check_approval(self, approval_id: str) -> dict[str, Any]:
        """Check the status of an approval request.

        Returns the request data merged with decision data if available.
        """
        request_path = self._dir / f"{approval_id}.json"
        if not request_path.exists():
            raise FileNotFoundError(f"Approval request not found: {approval_id}")

        request_data = json.loads(request_path.read_text(encoding="utf-8"))

        decision_path = self._dir / f"{approval_id}.decision.json"
        if decision_path.exists():
            decision_data = json.loads(decision_path.read_text(encoding="utf-8"))
            request_data["status"] = decision_data.get("decision", "pending")
            request_data["decision"] = decision_data
        return request_data

    def decide(
        self,
        approval_id: str,
        decision: str,  # "approve" or "reject"
        *,
        decided_by: str = "developer",
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a decision for an approval request."""
        request_path = self._dir / f"{approval_id}.json"
        if not request_path.exists():
            raise FileNotFoundError(f"Approval request not found: {approval_id}")

        decision_data = {
            "approval_id": approval_id,
            "decision": decision,
            "decided_by": decided_by,
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        }

        decision_path = self._dir / f"{approval_id}.decision.json"
        decision_path.write_text(
            json.dumps(decision_data, indent=2), encoding="utf-8"
        )
        return decision_data

    def list_pending(self) -> list[dict[str, Any]]:
        """Return all approval requests that have no decision yet."""
        pending: list[dict[str, Any]] = []
        for request_path in self._dir.glob("appr_*.json"):
            if request_path.name.endswith(".decision.json"):
                continue
            approval_id = request_path.stem
            decision_path = self._dir / f"{approval_id}.decision.json"
            if not decision_path.exists():
                data = json.loads(request_path.read_text(encoding="utf-8"))
                pending.append(data)
        return pending
