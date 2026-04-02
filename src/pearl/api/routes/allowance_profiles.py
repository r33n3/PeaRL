"""Agent Allowance Profile API routes.

Three-layer enforcement:
  1. Baseline rules per agent type (blocked_commands, blocked_paths, pre_approved_actions)
  2. Environment tier overrides (permissive/standard/strict/locked)
  3. Per-task extensions from TaskPacket (allowed_paths, pre_approved_commands)
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import RequireOperator, RequireViewer, get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.allowance_profile_repo import AllowanceProfileRepository
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["AllowanceProfiles"])


class AllowanceProfileCreate(BaseModel):
    name: str
    agent_type: str
    blocked_commands: list[str] = []
    blocked_paths: list[str] = []
    pre_approved_actions: list[str] = []
    model_restrictions: list[str] = []
    budget_cap_usd: float | None = None
    env_tier_overrides: dict = {}
    project_id: str | None = None


class AllowanceProfileUpdate(BaseModel):
    name: str | None = None
    blocked_commands: list[str] | None = None
    blocked_paths: list[str] | None = None
    pre_approved_actions: list[str] | None = None
    model_restrictions: list[str] | None = None
    budget_cap_usd: float | None = None
    env_tier_overrides: dict | None = None


class CheckRequest(BaseModel):
    action: str
    agent_id: str
    task_packet_id: str | None = None


def _profile_to_dict(row) -> dict:
    return {
        "profile_id": row.profile_id,
        "name": row.name,
        "agent_type": row.agent_type,
        "blocked_commands": row.blocked_commands or [],
        "blocked_paths": row.blocked_paths or [],
        "pre_approved_actions": row.pre_approved_actions or [],
        "model_restrictions": row.model_restrictions or [],
        "budget_cap_usd": row.budget_cap_usd,
        "env_tier_overrides": row.env_tier_overrides or {},
        "project_id": row.project_id,
        "profile_version": row.profile_version,
    }


def _resolve_allowance(profile_row, task_packet_row) -> dict:
    """Merge all three layers into a resolved allowance dict."""
    environment = task_packet_row.environment if task_packet_row else None

    blocked_commands = list(profile_row.blocked_commands or [])
    blocked_paths = list(profile_row.blocked_paths or [])
    pre_approved_actions = list(profile_row.pre_approved_actions or [])
    model_restrictions = list(profile_row.model_restrictions or [])
    budget_cap_usd = profile_row.budget_cap_usd

    # Layer 2 — apply env tier overrides (tighter constraints win)
    overrides = (profile_row.env_tier_overrides or {}).get(environment or "", {})
    if overrides:
        if "blocked_commands" in overrides:
            blocked_commands = list(set(blocked_commands) | set(overrides["blocked_commands"]))
        if "blocked_paths" in overrides:
            blocked_paths = list(set(blocked_paths) | set(overrides["blocked_paths"]))
        if "model_restrictions" in overrides:
            model_restrictions = list(set(model_restrictions) | set(overrides["model_restrictions"]))
        if "budget_cap_usd" in overrides:
            cap = overrides["budget_cap_usd"]
            if budget_cap_usd is None or cap < budget_cap_usd:
                budget_cap_usd = cap

    # Layer 3 — per-task grants
    task_allowed_paths: list[str] = []
    task_pre_approved: list[str] = []
    if task_packet_row:
        task_allowed_paths = list(task_packet_row.allowed_paths or [])
        task_pre_approved = list(task_packet_row.pre_approved_commands or [])

    return {
        "blocked_commands": blocked_commands,
        "blocked_paths": blocked_paths,
        "pre_approved_actions": pre_approved_actions + task_pre_approved,
        "model_restrictions": model_restrictions,
        "budget_cap_usd": budget_cap_usd,
        "task_allowed_paths": task_allowed_paths,
        "environment": environment,
    }


def _evaluate_action(action: str, resolved: dict) -> dict:
    """Evaluate action against resolved allowance. Returns check result."""
    pre_approved = resolved["pre_approved_actions"]

    # Pre-approved actions pass regardless of block rules
    for approved in pre_approved:
        if approved in action or action == approved:
            return {"allowed": True, "reason": "pre_approved", "layer": "task_extension", "matched_rule": approved}

    # Check blocked commands (Layer 1/2)
    for cmd in resolved["blocked_commands"]:
        if cmd in action:
            return {"allowed": False, "reason": "blocked_commands", "layer": "baseline", "matched_rule": cmd}

    # Check blocked paths (Layer 1/2) — skip if in task_allowed_paths (Layer 3)
    task_allowed = resolved["task_allowed_paths"]
    for path in resolved["blocked_paths"]:
        if path in action:
            # Check if task grants access to this path
            granted = any(path.startswith(tp) or tp in path for tp in task_allowed)
            if not granted:
                return {"allowed": False, "reason": "blocked_paths", "layer": "baseline", "matched_rule": path}

    return {"allowed": True, "reason": "default_allow", "layer": "baseline", "matched_rule": None}


@router.post("/allowance-profiles", status_code=201, dependencies=[RequireOperator])
async def create_allowance_profile(
    body: AllowanceProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = AllowanceProfileRepository(db)
    row = await repo.create(
        profile_id=generate_id("alp_"),
        name=body.name,
        agent_type=body.agent_type,
        blocked_commands=body.blocked_commands,
        blocked_paths=body.blocked_paths,
        pre_approved_actions=body.pre_approved_actions,
        model_restrictions=body.model_restrictions,
        budget_cap_usd=body.budget_cap_usd,
        env_tier_overrides=body.env_tier_overrides,
        project_id=body.project_id,
    )
    await db.commit()
    return _profile_to_dict(row)


@router.get("/allowance-profiles/{profile_id}", status_code=200, dependencies=[RequireViewer])
async def get_allowance_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = AllowanceProfileRepository(db)
    row = await repo.get(profile_id)
    if not row:
        raise NotFoundError("AllowanceProfile", profile_id)
    return _profile_to_dict(row)


@router.put("/allowance-profiles/{profile_id}", status_code=200, dependencies=[RequireOperator])
async def update_allowance_profile(
    profile_id: str,
    body: AllowanceProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = AllowanceProfileRepository(db)
    row = await repo.get(profile_id)
    if not row:
        raise NotFoundError("AllowanceProfile", profile_id)

    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    row = await repo.update(row, **updates)
    row.profile_version = (row.profile_version or 0) + 1
    await db.commit()
    return _profile_to_dict(row)


@router.post("/allowance-profiles/{profile_id}/check", status_code=200)
async def check_action(
    profile_id: str,
    body: CheckRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Evaluate whether an action is allowed under the resolved 3-layer profile."""
    profile_repo = AllowanceProfileRepository(db)
    profile = await profile_repo.get(profile_id)
    if not profile:
        raise NotFoundError("AllowanceProfile", profile_id)

    task_packet = None
    if body.task_packet_id:
        tp_repo = TaskPacketRepository(db)
        task_packet = await tp_repo.get(body.task_packet_id)

    resolved = _resolve_allowance(profile, task_packet)
    return _evaluate_action(body.action, resolved)


@router.get("/task-packets/{packet_id}/allowance", status_code=200)
async def get_task_allowance(
    packet_id: str,
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the fully resolved 3-layer merged allowance for a task packet + profile."""
    tp_repo = TaskPacketRepository(db)
    task_packet = await tp_repo.get(packet_id)
    if not task_packet:
        raise NotFoundError("TaskPacket", packet_id)

    profile_repo = AllowanceProfileRepository(db)
    profile = await profile_repo.get(profile_id)
    if not profile:
        raise NotFoundError("AllowanceProfile", profile_id)

    resolved = _resolve_allowance(profile, task_packet)
    resolved["profile_id"] = profile_id
    resolved["task_packet_id"] = packet_id
    return resolved
