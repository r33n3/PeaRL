"""Integration tests for the FACTORY_RUN_SUMMARY_PRESENT gate rule.

Tests exercise the private evaluator function directly with a mock eval context,
verifying the three verdict paths: pass, no-summary fail, anomaly fail.
"""

from __future__ import annotations

import pytest

from pearl.services.promotion.gate_evaluator import (
    _EvalContext,
    _eval_factory_run_summary_present,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    *,
    has_factory_run_summary: bool = False,
    factory_run_anomaly_count: int = 0,
) -> _EvalContext:
    """Build a minimal _EvalContext with only factory run fields set."""
    ctx = _EvalContext()
    ctx.has_factory_run_summary = has_factory_run_summary
    ctx.factory_run_anomaly_count = factory_run_anomaly_count
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_factory_run_summary_present_gate_passes_when_summary_exists():
    """Gate passes when a run summary exists and there are no anomaly flags."""
    ctx = _make_ctx(has_factory_run_summary=True, factory_run_anomaly_count=0)
    passed, message, detail = _eval_factory_run_summary_present(None, ctx)

    assert passed is True
    assert "present" in message.lower() and "no anomaly" in message.lower()


def test_factory_run_summary_present_gate_fails_when_no_summary():
    """Gate fails with a clear message when no run summary exists."""
    ctx = _make_ctx(has_factory_run_summary=False)
    passed, message, detail = _eval_factory_run_summary_present(None, ctx)

    assert passed is False
    assert "No factory run summary" in message


def test_factory_run_summary_present_gate_fails_when_anomalies():
    """Gate fails and includes anomaly count in detail when anomalies exist."""
    ctx = _make_ctx(has_factory_run_summary=True, factory_run_anomaly_count=3)
    passed, message, detail = _eval_factory_run_summary_present(None, ctx)

    assert passed is False
    assert "anomaly" in message.lower()
    assert detail is not None
    assert detail.get("anomaly_count") == 3
