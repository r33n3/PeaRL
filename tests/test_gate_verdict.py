# tests/test_gate_verdict.py
"""Tests for verdict.risk_level in AI_RISK_ACCEPTABLE gate evaluation."""
import pytest
from unittest.mock import MagicMock


def _make_ctx(mass_scan_seen=True, risk_score=2.0, verdict_risk_level=None):
    """Build a minimal _EvalContext for gate evaluation tests."""
    from pearl.services.promotion.gate_evaluator import _EvalContext
    ctx = _EvalContext()
    ctx.mass_scan_seen = mass_scan_seen
    ctx.mass_risk_score = risk_score
    ctx.mass_verdict_risk_level = verdict_risk_level
    ctx.open_findings = []
    ctx.mass_scan_completed = mass_scan_seen
    return ctx


def _make_rule(threshold=7.0):
    rule = MagicMock()
    rule.threshold = threshold
    return rule


def test_high_verdict_blocks_even_with_acceptable_score():
    """risk_level='high' blocks the gate even when numeric risk_score is low."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level="high")
    rule = _make_rule(threshold=7.0)
    passed, message, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert not passed
    assert "high" in message.lower()


def test_critical_verdict_blocks():
    """risk_level='critical' blocks the gate."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=1.0, verdict_risk_level="critical")
    rule = _make_rule()
    passed, message, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert not passed


def test_low_verdict_passes_with_acceptable_score():
    """risk_level='low' + acceptable score → passes."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level="low")
    rule = _make_rule()
    passed, _, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert passed


def test_missing_verdict_falls_back_to_score():
    """No verdict → existing numeric risk_score logic applies."""
    from pearl.services.promotion.gate_evaluator import _eval_ai_risk_acceptable
    ctx = _make_ctx(risk_score=2.0, verdict_risk_level=None)
    rule = _make_rule()
    passed, _, _ = _eval_ai_risk_acceptable(rule, ctx)
    assert passed
