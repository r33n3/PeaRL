"""ACoP §7.2 — pre-call enforcement endpoint.

Single REST endpoint that any enforcement consumer (API gateways, CI/CD pipelines,
non-MCP agents) can call to get permit | block | escalate before invoking a tool.
Internal MCP enforcement via FastAPI Depends() is unaffected — this is an additional
facade for external consumers.
"""

import hashlib
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.repositories.compiled_package_repo import CompiledPackageRepository

router = APIRouter(tags=["Enforcement"])


class PreCallRequest(BaseModel):
    agent_id: str
    contract_id: str  # compiled package_id — the ACoP Contract Object identifier
    environment: str | None = None
    action_type: str | None = None
    tool_name: str | None = None
    context: dict | None = None


@router.post("/enforcement/pre-call")
async def pre_call_check(
    body: PreCallRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Evaluate whether an agent action is permitted under its compiled contract.

    Returns one of:
      - ``{"decision": "permit", ...}`` — action is allowed
      - ``{"decision": "block", "reason": "...", "anomaly_code": "..."}`` — action denied
      - ``{"decision": "escalate", "cheq_request": {...}}`` — human approval required
    """
    # 1. Load compiled package (Contract Object) by contract_id
    repo = CompiledPackageRepository(db)
    pkg_row = await repo.get(body.contract_id)
    if not pkg_row:
        return {
            "decision": "block",
            "reason": "contract_not_found",
            "contract_id": body.contract_id,
        }

    pkg_data = pkg_row.package_data

    # 2. CIH verification — recompute hash to detect tampering (BA-05)
    stored_hash = pkg_data.get("package_metadata", {}).get("integrity", {}).get("hash")
    compiled_at_str = pkg_data.get("package_metadata", {}).get("integrity", {}).get("compiled_at")

    body_for_hash = json.loads(json.dumps(pkg_data))
    body_for_hash.pop("integrity_hash", None)  # ACoP CIH field — exclude from hash
    body_for_hash["package_metadata"]["integrity"] = {"compiled_at": compiled_at_str}
    canonical = json.dumps(body_for_hash, sort_keys=True, separators=(",", ":"))
    computed_hash = hashlib.sha256(canonical.encode()).hexdigest()

    if stored_hash is None or stored_hash != computed_hash:
        return {
            "decision": "block",
            "reason": "contract_integrity_failure",
            "anomaly_code": "BA-05",
            "contract_id": body.contract_id,
        }

    contract_env = pkg_data.get("project_identity", {}).get("environment", "")
    tool_constraints = pkg_data.get("tool_and_model_constraints", {})

    # 3. Environment mismatch check (BA-02)
    if body.environment and body.environment != contract_env:
        return {
            "decision": "block",
            "reason": "environment_mismatch",
            "anomaly_code": "BA-02",
            "contract_environment": contract_env,
            "requested_environment": body.environment,
        }

    # 4. Tool forbidden check (BA-04)
    if body.tool_name:
        forbidden = tool_constraints.get("forbidden_tool_classes", [])
        if body.tool_name in forbidden:
            return {
                "decision": "block",
                "reason": "tool_forbidden",
                "anomaly_code": "BA-04",
                "tool_name": body.tool_name,
            }

    # 5. Approval checkpoint escalation — check if action_type requires human approval
    if body.action_type:
        checkpoints = pkg_data.get("approval_checkpoints", [])
        for cp in checkpoints:
            if cp.get("trigger") == body.action_type:
                return {
                    "decision": "escalate",
                    "reason": "approval_checkpoint_required",
                    "checkpoint_id": cp.get("checkpoint_id"),
                    "required_roles": cp.get("required_roles", []),
                    "cheq_request": {
                        "action": body.action_type,
                        "contract_id": body.contract_id,
                        "agent_id": body.agent_id,
                        "environment": body.environment or contract_env,
                        "context": body.context,
                    },
                }

    # 6. Permit
    return {
        "decision": "permit",
        "contract_id": body.contract_id,
        "environment": contract_env,
        "integrity_hash": pkg_row.integrity_hash,
        "permitted_tools": tool_constraints.get("allowed_tool_classes", []),
    }
