"""Core policy engine — pre-indexed O(1) checks against compiled context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pearl.models.compiled_context import ApprovalCheckpoint, CompiledContextPackage


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    policy_ref: str = ""


@dataclass(frozen=True)
class PolicyViolation:
    pattern: str
    description: str
    line: int | None = None
    snippet: str = ""


# Patterns to detect prohibited patterns in diffs
_PATTERN_REGEXES: dict[str, re.Pattern[str]] = {
    "hardcoded_secrets": re.compile(
        r"""(?i)(?:"""
        r"""(?:api[_-]?key|secret|password|token|credential)\s*[:=]\s*['"][^'"]{8,}['"]"""
        r"""|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----)""",
        re.MULTILINE,
    ),
    "wildcard_iam_permissions": re.compile(
        r"""(?:["']?\*["']?\s*$|Action.*:\s*["']\*["'])""",
        re.MULTILINE,
    ),
    "undeclared_external_egress": re.compile(
        r"""(?i)(?:requests\.(?:get|post|put|delete|patch)\s*\(|httpx\.\w+\s*\(|urllib\.request\.urlopen|fetch\s*\()""",
        re.MULTILINE,
    ),
}


class PolicyEngine:
    """Evaluates actions and diffs against a compiled context package.

    All policy data is pre-indexed at construction time for O(1) set-membership checks.
    """

    def __init__(self, package: CompiledContextPackage) -> None:
        self._package = package

        ap = package.autonomy_policy
        self._allowed_actions = frozenset(ap.allowed_actions)
        self._blocked_actions = frozenset(ap.blocked_actions)
        self._approval_required = frozenset(ap.approval_required_for or [])

        sr = package.security_requirements
        self._prohibited_patterns = frozenset(sr.prohibited_patterns or [])

        nr = package.network_requirements
        self._outbound_allowlist = frozenset(
            (nr.outbound_allowlist or []) if nr else []
        )
        self._public_egress_forbidden = (nr.public_egress_forbidden or False) if nr else False

        dh = package.data_handling_requirements
        self._prohibited_in_context = frozenset(
            (dh.prohibited_in_model_context or []) if dh else []
        )

        tc = package.tool_and_model_constraints
        self._forbidden_tool_classes = frozenset(
            (tc.forbidden_tool_classes or []) if tc else []
        )

        # Map trigger -> checkpoint for quick lookup
        self._approval_triggers: dict[str, ApprovalCheckpoint] = {}
        for cp in package.approval_checkpoints or []:
            self._approval_triggers[cp.trigger] = cp

    # ── Action checks ────────────────────────────────────────────────────

    def check_action(self, action: str) -> PolicyResult:
        """Check whether *action* is allowed, blocked, or requires approval.

        Evaluation order: blocked > approval_required > allowed > default block.
        """
        if action in self._blocked_actions:
            return PolicyResult(
                decision=Decision.BLOCK,
                reason=f"Action '{action}' is in blocked_actions",
                policy_ref="autonomy_policy.blocked_actions",
            )

        if action in self._approval_required:
            return PolicyResult(
                decision=Decision.APPROVAL_REQUIRED,
                reason=f"Action '{action}' requires approval",
                policy_ref="autonomy_policy.approval_required_for",
            )

        if action in self._allowed_actions:
            return PolicyResult(
                decision=Decision.ALLOW,
                reason=f"Action '{action}' is in allowed_actions",
                policy_ref="autonomy_policy.allowed_actions",
            )

        # Deny by default
        return PolicyResult(
            decision=Decision.BLOCK,
            reason=f"Action '{action}' is not in allowed_actions (deny-by-default)",
            policy_ref="autonomy_policy.deny_by_default",
        )

    # ── Diff checks ──────────────────────────────────────────────────────

    def check_diff(self, diff_text: str) -> list[PolicyViolation]:
        """Scan *diff_text* for prohibited patterns."""
        violations: list[PolicyViolation] = []
        lines = diff_text.splitlines()

        for pattern_name in self._prohibited_patterns:
            regex = _PATTERN_REGEXES.get(pattern_name)
            if not regex:
                continue
            for i, line in enumerate(lines, start=1):
                if not line.startswith("+"):
                    continue  # Only check added lines
                if regex.search(line):
                    violations.append(
                        PolicyViolation(
                            pattern=pattern_name,
                            description=f"Prohibited pattern '{pattern_name}' detected",
                            line=i,
                            snippet=line[:120],
                        )
                    )
        return violations

    # ── Network checks ───────────────────────────────────────────────────

    def check_network(self, host: str) -> PolicyResult:
        """Check if *host* is in the outbound allowlist."""
        if not self._public_egress_forbidden:
            return PolicyResult(
                decision=Decision.ALLOW,
                reason="Public egress is not forbidden",
                policy_ref="network_requirements.public_egress_forbidden",
            )

        if host in self._outbound_allowlist:
            return PolicyResult(
                decision=Decision.ALLOW,
                reason=f"Host '{host}' is in outbound_allowlist",
                policy_ref="network_requirements.outbound_allowlist",
            )

        return PolicyResult(
            decision=Decision.BLOCK,
            reason=f"Host '{host}' is not in outbound_allowlist",
            policy_ref="network_requirements.outbound_allowlist",
        )

    # ── Required tests ───────────────────────────────────────────────────

    def get_required_tests(self, task_type: str) -> list[str]:
        """Return required tests for the given task type."""
        rt = self._package.required_tests
        if not rt:
            return []
        result: list[str] = []
        if rt.security:
            result.extend(rt.security)
        if rt.rai:
            result.extend(rt.rai)
        if rt.functional:
            result.extend(rt.functional)
        return result

    # ── Policy summary ───────────────────────────────────────────────────

    def get_policy_summary(self) -> dict:
        """Return a human-readable policy summary."""
        p = self._package
        return {
            "project_id": p.project_identity.project_id,
            "environment": p.project_identity.environment,
            "autonomy_mode": p.autonomy_policy.mode,
            "allowed_actions": sorted(self._allowed_actions),
            "blocked_actions": sorted(self._blocked_actions),
            "approval_required_for": sorted(self._approval_required),
            "prohibited_patterns": sorted(self._prohibited_patterns),
            "outbound_allowlist": sorted(self._outbound_allowlist),
            "required_tests": self.get_required_tests("feature"),
            "approval_checkpoints": [
                {"trigger": cp.trigger, "roles": cp.required_roles}
                for cp in (p.approval_checkpoints or [])
            ],
        }

    # ── Accessors ────────────────────────────────────────────────────────

    @property
    def package(self) -> CompiledContextPackage:
        return self._package

    @property
    def prohibited_in_context(self) -> frozenset[str]:
        return self._prohibited_in_context

    @property
    def forbidden_tool_classes(self) -> frozenset[str]:
        return self._forbidden_tool_classes
