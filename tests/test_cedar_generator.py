"""Unit tests for CedarPolicyGenerator — pure logic, no DB."""

import hashlib
import json

import pytest

from pearl.integrations.agentcore.cedar_generator import (
    CedarBundle,
    CedarPolicy,
    CedarPolicyGenerator,
)


@pytest.fixture
def generator():
    return CedarPolicyGenerator()


def test_generate_bundle_returns_cedar_bundle(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="arn:aws:bedrock-agentcore:us-east-1:123:gateway/gw1",
    )
    assert isinstance(bundle, CedarBundle)
    assert bundle.bundle_hash
    assert len(bundle.policies) >= 1  # at least the deny-all baseline


def test_deny_all_baseline_always_present(generator):
    bundle = generator.generate_bundle(org_id="org_test", gateway_arn="")
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_deny_all_baseline" in ids


def test_deny_all_statement_has_forbid(generator):
    bundle = generator.generate_bundle(org_id="org_test", gateway_arn="")
    deny = next(p for p in bundle.policies if p.policy_id == "pearl_deny_all_baseline")
    assert "forbid(" in deny.statement
    assert "pearl_approved" in deny.statement


def test_permit_role_generated_for_default_roles(generator):
    bundle = generator.generate_bundle(org_id="org_test", gateway_arn="")
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_permit_role_operator" in ids
    assert "pearl_permit_role_admin" in ids


def test_permit_role_viewer_is_read_only(generator):
    bundle = generator.generate_bundle(
        org_id="org_test", gateway_arn="", allowed_roles=["viewer"]
    )
    viewer_policy = next(
        p for p in bundle.policies if p.policy_id == "pearl_permit_role_viewer"
    )
    assert "DescribeAgent" in viewer_policy.statement
    assert "InvokeFoundationModel" not in viewer_policy.statement


def test_agent_alias_permit_generated(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        agent_aliases=[{"alias_id": "alias_abc", "name": "TestAgent", "environment": "dev"}],
    )
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_permit_alias_alias_abc_dev" in ids


def test_agent_alias_statement_contains_alias_id(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        agent_aliases=[{"alias_id": "alias_xyz", "environment": "prod"}],
    )
    alias_policy = next(
        p for p in bundle.policies if "alias_xyz" in p.policy_id
    )
    assert '"alias_xyz"' in alias_policy.statement
    assert '"prod"' in alias_policy.statement


def test_blocking_rule_type_produces_forbid(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        blocked_rule_types=["no_hardcoded_secrets"],
    )
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_forbid_no_hardcoded_secrets" in ids


def test_unknown_rule_type_ignored(generator):
    # Unknown rule types should not crash or produce a policy
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        blocked_rule_types=["nonexistent_rule"],
    )
    ids = {p.policy_id for p in bundle.policies}
    assert not any("nonexistent_rule" in pid for pid in ids)


def test_baseline_max_tokens_constraint(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        baseline_controls={"max_context_tokens": 4096},
    )
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_baseline_max_tokens" in ids
    max_policy = next(p for p in bundle.policies if p.policy_id == "pearl_baseline_max_tokens")
    assert "4096" in max_policy.statement


def test_baseline_allowed_models_constraint(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        baseline_controls={"allowed_model_ids": ["claude-3-5-sonnet-20241022", "claude-3-haiku"]},
    )
    ids = {p.policy_id for p in bundle.policies}
    assert "pearl_baseline_allowed_models" in ids
    policy = next(p for p in bundle.policies if p.policy_id == "pearl_baseline_allowed_models")
    assert "claude-3-5-sonnet-20241022" in policy.statement


def test_bundle_hash_is_sha256_hex(generator):
    bundle = generator.generate_bundle(org_id="org_test", gateway_arn="")
    assert len(bundle.bundle_hash) == 64
    int(bundle.bundle_hash, 16)  # should not raise


def test_bundle_hash_is_deterministic(generator):
    b1 = generator.generate_bundle(org_id="org_same", gateway_arn="arn:test")
    b2 = generator.generate_bundle(org_id="org_same", gateway_arn="arn:test")
    assert b1.bundle_hash == b2.bundle_hash


def test_bundle_hash_changes_with_different_org(generator):
    b1 = generator.generate_bundle(org_id="org_a", gateway_arn="")
    b2 = generator.generate_bundle(org_id="org_b", gateway_arn="")
    assert b1.bundle_hash != b2.bundle_hash


def test_bundle_hash_changes_with_different_policies(generator):
    b1 = generator.generate_bundle(org_id="org_test", gateway_arn="")
    b2 = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        blocked_rule_types=["critical_findings_zero"],
    )
    assert b1.bundle_hash != b2.bundle_hash


def test_to_json_dict_structure(generator):
    bundle = generator.generate_bundle(org_id="org_test", gateway_arn="arn:test")
    d = bundle.to_json_dict()
    assert "policies" in d
    assert "static" in d["policies"]
    assert "metadata" in d
    assert d["metadata"]["org_id"] == "org_test"
    assert d["metadata"]["generator"] == "pearl"


def test_to_json_dict_contains_all_policy_ids(generator):
    bundle = generator.generate_bundle(
        org_id="org_test",
        gateway_arn="",
        allowed_roles=["operator"],
        agent_aliases=[{"alias_id": "a1", "environment": "dev"}],
    )
    d = bundle.to_json_dict()
    static = d["policies"]["static"]
    for policy in bundle.policies:
        assert policy.policy_id in static


def test_bundle_hash_recomputes_from_json(generator):
    """Hash in CedarBundle should match SHA-256 of canonical bundle JSON."""
    bundle = generator.generate_bundle(org_id="org_verify", gateway_arn="arn:x")
    d = bundle.to_json_dict()
    # Reconstruct the dict that was hashed
    bundle_dict = {
        "policies": d["policies"],
        "metadata": d["metadata"],
    }
    expected_hash = hashlib.sha256(
        json.dumps(bundle_dict, sort_keys=True).encode()
    ).hexdigest()
    assert bundle.bundle_hash == expected_hash


def test_multiple_blocked_rules_all_produce_forbids(generator):
    rules = ["no_hardcoded_secrets", "critical_findings_zero", "iam_roles_defined"]
    bundle = generator.generate_bundle(
        org_id="org_test", gateway_arn="", blocked_rule_types=rules
    )
    ids = {p.policy_id for p in bundle.policies}
    for rule in rules:
        assert f"pearl_forbid_{rule}" in ids
