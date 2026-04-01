"""Integration tests for Agent Allowance Profiles — 3-layer enforcement."""

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _create_profile(client, **overrides) -> dict:
    """Create a profile via API; client should have operator/admin role (reviewer_client)."""
    payload = {
        "name": "Test Profile",
        "agent_type": "remediation_agent",
        "blocked_commands": ["rm -rf", "dd if="],
        "blocked_paths": ["/etc/passwd", "/etc/shadow"],
        "pre_approved_actions": ["git status", "pytest"],
        "model_restrictions": [],
        "budget_cap_usd": 10.0,
        "env_tier_overrides": {},
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/allowance-profiles", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── Model and CRUD ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_allowance_profile(reviewer_client):
    body = await _create_profile(reviewer_client)
    assert body["profile_id"].startswith("alp_")
    assert body["name"] == "Test Profile"
    assert body["agent_type"] == "remediation_agent"
    assert "rm -rf" in body["blocked_commands"]


@pytest.mark.asyncio
async def test_get_allowance_profile(reviewer_client):
    created = await _create_profile(reviewer_client)
    resp = await reviewer_client.get(f"/api/v1/allowance-profiles/{created['profile_id']}")
    assert resp.status_code == 200
    assert resp.json()["profile_id"] == created["profile_id"]


@pytest.mark.asyncio
async def test_get_allowance_profile_not_found(reviewer_client):
    resp = await reviewer_client.get("/api/v1/allowance-profiles/alp_nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_allowance_profile(reviewer_client):
    created = await _create_profile(reviewer_client)
    resp = await reviewer_client.put(
        f"/api/v1/allowance-profiles/{created['profile_id']}",
        json={"name": "Updated Profile", "budget_cap_usd": 5.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Profile"
    assert body["budget_cap_usd"] == 5.0


# ─── Check endpoint — Layer 1 baseline ───────────────────────────────────────

@pytest.mark.asyncio
async def test_check_blocked_command_denied(reviewer_client, client):
    """Blocked command is denied at baseline layer."""
    profile = await _create_profile(reviewer_client)
    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "rm -rf /tmp/data", "agent_id": "agent_test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "blocked_commands"
    assert body["layer"] == "baseline"
    assert body["matched_rule"] == "rm -rf"


@pytest.mark.asyncio
async def test_check_blocked_path_denied(reviewer_client, client):
    """Blocked path is denied at baseline layer."""
    profile = await _create_profile(reviewer_client)
    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "cat /etc/passwd", "agent_id": "agent_test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "blocked_paths"
    assert body["layer"] == "baseline"


@pytest.mark.asyncio
async def test_check_pre_approved_action_passes(reviewer_client, client):
    """Pre-approved action passes regardless of other rules."""
    profile = await _create_profile(reviewer_client)
    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "pytest tests/", "agent_id": "agent_test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True
    assert body["reason"] == "pre_approved"


@pytest.mark.asyncio
async def test_check_default_allow(reviewer_client, client):
    """Action not matching any rule defaults to allowed."""
    profile = await _create_profile(reviewer_client)
    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "git commit -m 'fix'", "agent_id": "agent_test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True
    assert body["reason"] == "default_allow"


# ─── Check endpoint — Layer 2 env tier overrides ──────────────────────────────

@pytest.mark.asyncio
async def test_env_tier_override_tightens_budget_cap(reviewer_client, client, db_session):
    """Environment tier override tightens budget_cap from baseline."""
    profile = await _create_profile(
        reviewer_client,
        budget_cap_usd=100.0,
        env_tier_overrides={"prod": {"budget_cap_usd": 5.0}},
    )
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_testprod001",
        project_id="proj_dummy",
        environment="prod",
        packet_data={"task_type": "test"},
        trace_id="trace_test",
    )
    await db_session.commit()

    # Fetch the resolved allowance — budget_cap_usd should be 5.0 (tighter wins)
    resp = await client.get(
        "/api/v1/task-packets/tp_testprod001/allowance",
        params={"profile_id": profile["profile_id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["budget_cap_usd"] == 5.0


@pytest.mark.asyncio
async def test_env_tier_override_adds_blocked_commands(reviewer_client, client, db_session):
    """Environment tier override in prod adds additional blocked commands."""
    profile = await _create_profile(
        reviewer_client,
        blocked_commands=["rm -rf"],
        env_tier_overrides={"prod": {"blocked_commands": ["curl http://"]}},
    )
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_prodblock001",
        project_id="proj_dummy",
        environment="prod",
        packet_data={},
        trace_id="trace_test",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "curl http://internal.api/secret", "agent_id": "agent_x", "task_packet_id": "tp_prodblock001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "blocked_commands"
    assert body["matched_rule"] == "curl http://"


# ─── Check endpoint — Layer 3 task packet extensions ─────────────────────────

@pytest.mark.asyncio
async def test_task_packet_path_extension_grants_access(reviewer_client, client, db_session):
    """Task packet allowed_paths grants access to a path blocked in baseline."""
    profile = await _create_profile(
        reviewer_client,
        blocked_paths=["/var/log/secret"],
    )
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_pathgrant001",
        project_id="proj_dummy",
        environment="dev",
        packet_data={},
        trace_id="trace_test",
        allowed_paths=["/var/log/secret"],
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "tail /var/log/secret/app.log", "agent_id": "agent_x", "task_packet_id": "tp_pathgrant001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True


@pytest.mark.asyncio
async def test_task_packet_pre_approved_command_passes(reviewer_client, client, db_session):
    """Task packet pre_approved_commands grants a command not in baseline."""
    profile = await _create_profile(reviewer_client, pre_approved_actions=[])
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_cmdgrant001",
        project_id="proj_dummy",
        environment="dev",
        packet_data={},
        trace_id="trace_test",
        pre_approved_commands=["make deploy-staging"],
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/allowance-profiles/{profile['profile_id']}/check",
        json={"action": "make deploy-staging", "agent_id": "agent_x", "task_packet_id": "tp_cmdgrant001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True
    assert body["reason"] == "pre_approved"


# ─── GET /task-packets/{id}/allowance ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_task_allowance_merged_profile(reviewer_client, client, db_session):
    """GET /task-packets/{id}/allowance returns fully resolved 3-layer dict."""
    profile = await _create_profile(
        reviewer_client,
        blocked_commands=["rm -rf"],
        env_tier_overrides={"staging": {"blocked_commands": ["curl"]}},
    )
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_allowance001",
        project_id="proj_dummy",
        environment="staging",
        packet_data={},
        trace_id="trace_test",
        allowed_paths=["/tmp/work"],
        pre_approved_commands=["git pull"],
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/task-packets/tp_allowance001/allowance",
        params={"profile_id": profile["profile_id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == profile["profile_id"]
    assert body["task_packet_id"] == "tp_allowance001"
    assert "rm -rf" in body["blocked_commands"]
    assert "curl" in body["blocked_commands"]
    assert "/tmp/work" in body["task_allowed_paths"]
    assert "git pull" in body["pre_approved_actions"]
    assert body["environment"] == "staging"


@pytest.mark.asyncio
async def test_get_task_allowance_not_found_packet(client):
    resp = await client.get(
        "/api/v1/task-packets/tp_nonexistent/allowance",
        params={"profile_id": "alp_dummy"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_task_allowance_not_found_profile(client, db_session):
    from pearl.repositories.task_packet_repo import TaskPacketRepository
    tp_repo = TaskPacketRepository(db_session)
    await tp_repo.create(
        task_packet_id="tp_noprofile001",
        project_id="proj_dummy",
        environment="dev",
        packet_data={},
        trace_id="trace_test",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/task-packets/tp_noprofile001/allowance",
        params={"profile_id": "alp_nonexistent"},
    )
    assert resp.status_code == 404
