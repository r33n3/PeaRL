"""Unit tests for AgentCore CloudWatch log analysis (CWD detectors)."""

import pytest

from pearl.integrations.agentcore.agentcore_cloudwatch import (
    AnalysisInput,
    DetectedFinding,
    analyse,
    extract_forbidden_actions,
    extract_registered_aliases,
    watermark_from_entries,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_entry(
    principal="alias_123",
    action="InvokeFoundationModel",
    decision="ALLOW",
    policy_hash="abc123",
    resource="bedrock/claude",
    timestamp="2026-03-18T10:00:00+00:00",
):
    return {
        "@timestamp": timestamp,
        "principalId": principal,
        "action": action,
        "resource": resource,
        "decision": decision,
        "policyHash": policy_hash,
        "requestId": "req_test",
    }


def _make_input(**overrides):
    defaults = dict(
        log_entries=[_make_entry()],
        active_bundle_hash="abc123",
        registered_alias_ids={"alias_123"},
        forbidden_actions=set(),
        baseline_call_rate=None,
        anomaly_threshold=3.0,
        org_id="org_test",
        project_id="proj_test",
        environment="prod",
    )
    defaults.update(overrides)
    return AnalysisInput(**defaults)


# ── analyse() ─────────────────────────────────────────────────────────────────

def test_analyse_no_findings_clean_input():
    inp = _make_input()
    findings = analyse(inp)
    assert findings == []


def test_analyse_empty_entries_returns_empty():
    inp = _make_input(log_entries=[])
    findings = analyse(inp)
    assert findings == []


# ── CWD-001: Policy hash drift ─────────────────────────────────────────────────

def test_cwd001_detected_when_hash_differs():
    entries = [_make_entry(policy_hash="different_hash")]
    inp = _make_input(log_entries=entries, active_bundle_hash="expected_hash")
    findings = analyse(inp)
    codes = [f.anomaly_code for f in findings]
    assert "CWD-001" in codes


def test_cwd001_not_detected_when_hashes_match():
    entries = [_make_entry(policy_hash="correct_hash")]
    inp = _make_input(log_entries=entries, active_bundle_hash="correct_hash")
    findings = analyse(inp)
    codes = [f.anomaly_code for f in findings]
    assert "CWD-001" not in codes


def test_cwd001_not_detected_when_no_active_hash():
    entries = [_make_entry(policy_hash="any_hash")]
    inp = _make_input(log_entries=entries, active_bundle_hash=None)
    findings = analyse(inp)
    codes = [f.anomaly_code for f in findings]
    assert "CWD-001" not in codes


def test_cwd001_severity_is_critical():
    entries = [_make_entry(policy_hash="wrong")]
    inp = _make_input(log_entries=entries, active_bundle_hash="right")
    findings = analyse(inp)
    cwd001 = next(f for f in findings if f.anomaly_code == "CWD-001")
    assert cwd001.severity == "critical"


def test_cwd001_details_contain_observed_hashes():
    entries = [_make_entry(policy_hash="h1"), _make_entry(policy_hash="h2")]
    inp = _make_input(log_entries=entries, active_bundle_hash="expected")
    cwd001 = next(f for f in analyse(inp) if f.anomaly_code == "CWD-001")
    assert "h1" in cwd001.details["observed_hashes"]
    assert "h2" in cwd001.details["observed_hashes"]


# ── CWD-002: Decision drift ────────────────────────────────────────────────────

def test_cwd002_detected_when_same_pair_has_allow_and_deny():
    entries = [
        _make_entry(principal="p1", action="InvokeFoundationModel", decision="ALLOW"),
        _make_entry(principal="p1", action="InvokeFoundationModel", decision="DENY"),
    ]
    inp = _make_input(log_entries=entries, active_bundle_hash=None)
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-002" in codes


def test_cwd002_not_detected_when_consistent_allow():
    entries = [
        _make_entry(principal="p1", action="InvokeFoundationModel", decision="ALLOW"),
        _make_entry(principal="p1", action="InvokeFoundationModel", decision="ALLOW"),
    ]
    inp = _make_input(log_entries=entries, active_bundle_hash=None)
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-002" not in codes


def test_cwd002_not_detected_when_consistent_deny():
    entries = [
        _make_entry(principal="p1", action="ExecApiCall", decision="DENY"),
        _make_entry(principal="p1", action="ExecApiCall", decision="DENY"),
    ]
    inp = _make_input(log_entries=entries, active_bundle_hash=None)
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-002" not in codes


def test_cwd002_different_principals_not_flagged():
    entries = [
        _make_entry(principal="p1", action="InvokeFoundationModel", decision="ALLOW"),
        _make_entry(principal="p2", action="InvokeFoundationModel", decision="DENY"),
    ]
    inp = _make_input(log_entries=entries, active_bundle_hash=None)
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-002" not in codes


# ── CWD-003: Agent sprawl ──────────────────────────────────────────────────────

def test_cwd003_detected_when_unknown_principal():
    entries = [_make_entry(principal="alias_unknown")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        registered_alias_ids={"alias_known"},
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-003" in codes


def test_cwd003_not_detected_when_principal_registered():
    entries = [_make_entry(principal="alias_registered")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        registered_alias_ids={"alias_registered"},
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-003" not in codes


def test_cwd003_skipped_when_no_registered_aliases():
    # If no aliases registered yet, don't spam false positives on initial setup
    entries = [_make_entry(principal="alias_any")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        registered_alias_ids=set(),
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-003" not in codes


def test_cwd003_severity_is_high():
    entries = [_make_entry(principal="alias_x")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        registered_alias_ids={"alias_other"},
    )
    cwd003 = next(f for f in analyse(inp) if f.anomaly_code == "CWD-003")
    assert cwd003.severity == "high"


# ── CWD-004: Governance bypass ─────────────────────────────────────────────────

def test_cwd004_detected_when_forbidden_action_allowed():
    entries = [_make_entry(action="ExecuteApiCall", decision="ALLOW")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        forbidden_actions={"ExecuteApiCall"},
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-004" in codes


def test_cwd004_not_triggered_when_forbidden_action_is_denied():
    entries = [_make_entry(action="ExecuteApiCall", decision="DENY")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        forbidden_actions={"ExecuteApiCall"},
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-004" not in codes


def test_cwd004_not_triggered_when_no_forbidden_actions():
    entries = [_make_entry(action="ExecuteApiCall", decision="ALLOW")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        forbidden_actions=set(),
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-004" not in codes


def test_cwd004_severity_is_critical():
    entries = [_make_entry(action="BadAction", decision="ALLOW")]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        forbidden_actions={"BadAction"},
    )
    cwd004 = next(f for f in analyse(inp) if f.anomaly_code == "CWD-004")
    assert cwd004.severity == "critical"


# ── CWD-005: Volume anomaly ────────────────────────────────────────────────────

def test_cwd005_detected_when_volume_spikes():
    # baseline = 4, sigma ≈ 2, threshold at 3σ = 10; 100 entries >> 10
    entries = [_make_entry() for _ in range(100)]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        baseline_call_rate=4.0,
        anomaly_threshold=3.0,
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-005" in codes


def test_cwd005_not_detected_when_volume_normal():
    entries = [_make_entry() for _ in range(4)]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        baseline_call_rate=4.0,
        anomaly_threshold=3.0,
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-005" not in codes


def test_cwd005_not_detected_when_no_baseline():
    entries = [_make_entry() for _ in range(1000)]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        baseline_call_rate=None,
    )
    codes = [f.anomaly_code for f in analyse(inp)]
    assert "CWD-005" not in codes


def test_cwd005_severity_is_moderate():
    entries = [_make_entry() for _ in range(100)]
    inp = _make_input(
        log_entries=entries,
        active_bundle_hash=None,
        baseline_call_rate=4.0,
        anomaly_threshold=3.0,
    )
    cwd005 = next(f for f in analyse(inp) if f.anomaly_code == "CWD-005")
    assert cwd005.severity == "moderate"


# ── extract_registered_aliases ────────────────────────────────────────────────

def test_extract_aliases_from_bundle_snapshot():
    snapshot = {
        "policies": {
            "static": {
                "pearl_permit_alias_alias_abc_dev": {"statement": "..."},
                "pearl_permit_alias_alias_xyz_prod": {"statement": "..."},
                "pearl_permit_role_operator": {"statement": "..."},
            }
        }
    }
    aliases = extract_registered_aliases(snapshot)
    assert "alias_abc" in aliases
    assert "alias_xyz" in aliases
    assert "operator" not in aliases


def test_extract_aliases_empty_snapshot():
    assert extract_registered_aliases(None) == set()
    assert extract_registered_aliases({}) == set()


# ── extract_forbidden_actions ─────────────────────────────────────────────────

def test_extract_forbidden_actions_from_bundle():
    snapshot = {
        "policies": {
            "static": {
                "pearl_forbid_no_hardcoded_secrets": {
                    "statement": 'forbid(\n  principal,\n  action == AgentCore::Action::"ExecuteApiCall",\n  resource\n);'
                },
                "pearl_forbid_critical_findings_zero": {
                    "statement": 'forbid(\n  principal,\n  action == AgentCore::Action::"InvokeFoundationModel",\n  resource\n);'
                },
            }
        }
    }
    forbidden = extract_forbidden_actions(snapshot)
    assert "ExecuteApiCall" in forbidden
    assert "InvokeFoundationModel" in forbidden


def test_extract_forbidden_actions_empty_snapshot():
    assert extract_forbidden_actions(None) == set()


# ── watermark_from_entries ────────────────────────────────────────────────────

def test_watermark_returns_latest_timestamp():
    entries = [
        _make_entry(timestamp="2026-03-18T10:00:00+00:00"),
        _make_entry(timestamp="2026-03-18T11:00:00+00:00"),
        _make_entry(timestamp="2026-03-18T09:00:00+00:00"),
    ]
    wm = watermark_from_entries(entries)
    assert wm is not None
    assert wm.hour == 11


def test_watermark_none_for_empty_entries():
    assert watermark_from_entries([]) is None


def test_watermark_skips_entries_without_timestamp():
    entries = [{"principalId": "p1"}]  # no @timestamp
    assert watermark_from_entries(entries) is None
