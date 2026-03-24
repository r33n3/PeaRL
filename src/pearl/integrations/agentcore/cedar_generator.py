"""Cedar policy bundle generator — translates PeaRL governance state into Cedar policies.

Cedar policies control what actions AgentCore agents can perform at runtime.
PeaRL is the governance authority; Cedar bundles are derived artifacts of PeaRL
approval decisions and org baseline settings.  Policies are generated here and
deployed to AgentCore via AgentCoreClient.  They must not be edited outside
PeaRL's governance workflow.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class CedarPolicy:
    policy_id: str
    statement: str
    description: str = ""


@dataclass
class CedarBundle:
    policies: list[CedarPolicy]
    bundle_hash: str
    metadata: dict = field(default_factory=dict)

    def to_json_dict(self) -> dict:
        """Serialize to the JSON structure expected by AgentCore put_gateway_policy."""
        return {
            "policies": {
                "static": {
                    p.policy_id: {"statement": p.statement}
                    for p in self.policies
                }
            },
            "metadata": self.metadata,
        }


class CedarPolicyGenerator:
    """Generates Cedar policy bundles from PeaRL governance state.

    Cedar is deny-by-default; every permit must be explicit.  PeaRL encodes:
      - Which agent aliases are registered and approved → permit clauses
      - Which gate rule types are currently blocking → forbid clauses
      - Org baseline runtime controls → resource-scoped forbid clauses

    The generated bundle is hashed (SHA-256 of canonical JSON) so CloudWatch
    drift detection (CWD-001) can detect out-of-band Cedar modifications.
    """

    _ACTION_NS = "AgentCore::Action"
    _AGENT_NS = "AgentCore::Agent"

    # Gate rule type → AgentCore action it should block when failing
    _RULE_TO_ACTION: dict[str, str] = {
        "no_hardcoded_secrets": "ExecuteApiCall",
        "critical_findings_zero": "InvokeFoundationModel",
        "high_findings_zero": "InvokeFoundationModel",
        "security_review_approval": "ExecuteApiCall",
        "pen_test_passed": "ExecuteApiCall",
        "compliance_controls_verified": "InvokeFoundationModel",
        "iam_roles_defined": "ExecuteApiCall",
        "network_boundaries_declared": "ExecuteApiCall",
    }

    def generate_bundle(
        self,
        org_id: str,
        gateway_arn: str,
        *,
        allowed_roles: list[str] | None = None,
        blocked_rule_types: list[str] | None = None,
        baseline_controls: dict | None = None,
        agent_aliases: list[dict] | None = None,
    ) -> CedarBundle:
        """Generate a Cedar bundle representing current PeaRL governance state.

        Parameters
        ----------
        org_id:
            Organisation identifier (embedded in bundle metadata).
        gateway_arn:
            AgentCore gateway ARN this bundle will be deployed to.
        allowed_roles:
            PeaRL roles that may invoke agents (default: operator, admin).
        blocked_rule_types:
            Gate rule types currently failing — each generates a forbid clause.
        baseline_controls:
            Dict from the org baseline document ``defaults`` block.
        agent_aliases:
            Registered agent aliases: list of ``{alias_id, name, environment}``.
        """
        policies: list[CedarPolicy] = []

        # 1. Explicit deny-all sentinel (Cedar is deny-by-default, but this
        #    makes the intent auditable in the bundle snapshot)
        policies.append(self._deny_all_baseline())

        # 2. Permit registered agent aliases
        for alias in (agent_aliases or []):
            policies.append(self._permit_agent_alias(alias))

        # 3. Permit PeaRL role groups
        for role in (allowed_roles or ["operator", "admin"]):
            policies.append(self._permit_role(role))

        # 4. Forbid clauses for failing gate rules
        for rule_type in (blocked_rule_types or []):
            forbid = self._rule_type_to_forbid(rule_type)
            if forbid:
                policies.append(forbid)

        # 5. Baseline-derived resource constraints
        for policy in self._baseline_to_constraints(baseline_controls or {}):
            policies.append(policy)

        bundle_dict = {
            "policies": {
                "static": {
                    p.policy_id: {"statement": p.statement}
                    for p in policies
                }
            },
            "metadata": {
                "org_id": org_id,
                "gateway_arn": gateway_arn,
                "generator": "pearl",
            },
        }
        bundle_hash = hashlib.sha256(
            json.dumps(bundle_dict, sort_keys=True).encode()
        ).hexdigest()

        return CedarBundle(
            policies=policies,
            bundle_hash=bundle_hash,
            metadata=bundle_dict["metadata"],
        )

    # ── policy builders ────────────────────────────────────────────────────────

    def _deny_all_baseline(self) -> CedarPolicy:
        return CedarPolicy(
            policy_id="pearl_deny_all_baseline",
            description="Explicit deny-all — Cedar is deny-by-default; this makes it auditable",
            statement=(
                "forbid(\n"
                "  principal,\n"
                "  action,\n"
                "  resource\n"
                ") unless {\n"
                "  principal has pearl_approved && principal.pearl_approved == true\n"
                "};"
            ),
        )

    def _permit_agent_alias(self, alias: dict) -> CedarPolicy:
        alias_id = alias.get("alias_id", "unknown")
        env = alias.get("environment", "dev")
        policy_id = f"pearl_permit_alias_{alias_id}_{env}"
        return CedarPolicy(
            policy_id=policy_id,
            description=f"Permit registered alias {alias_id} ({env})",
            statement=(
                f"permit(\n"
                f"  principal == {self._AGENT_NS}::\"{alias_id}\",\n"
                f"  action in [{self._ACTION_NS}::\"InvokeFoundationModel\",\n"
                f"             {self._ACTION_NS}::\"ExecuteApiCall\"],\n"
                f"  resource\n"
                f") when {{\n"
                f"  principal.pearl_approved == true &&\n"
                f"  principal.environment == \"{env}\"\n"
                f"}};"
            ),
        )

    def _permit_role(self, role: str) -> CedarPolicy:
        if role == "viewer":
            action_clause = f"{self._ACTION_NS}::\"DescribeAgent\""
        else:
            action_clause = (
                f"{self._ACTION_NS}::\"InvokeFoundationModel\",\n"
                f"                 {self._ACTION_NS}::\"ExecuteApiCall\",\n"
                f"                 {self._ACTION_NS}::\"RetrieveFromKnowledgeBase\""
            )
            action_clause = f"[{action_clause}]"
        return CedarPolicy(
            policy_id=f"pearl_permit_role_{role}",
            description=f"Permit PeaRL role group: {role}",
            statement=(
                f"permit(\n"
                f"  principal in AgentCore::Group::\"{role}\",\n"
                f"  action in {action_clause},\n"
                f"  resource\n"
                f") when {{\n"
                f"  principal.pearl_role == \"{role}\"\n"
                f"}};"
            ),
        )

    def _rule_type_to_forbid(self, rule_type: str) -> CedarPolicy | None:
        action = self._RULE_TO_ACTION.get(rule_type)
        if not action:
            return None
        attr = f"pearl_gate_{rule_type}_passed"
        return CedarPolicy(
            policy_id=f"pearl_forbid_{rule_type}",
            description=f"Forbid {action} — gate rule {rule_type} is blocking",
            statement=(
                f"forbid(\n"
                f"  principal,\n"
                f"  action == {self._ACTION_NS}::\"{action}\",\n"
                f"  resource\n"
                f") when {{\n"
                f"  !(principal has {attr}) ||\n"
                f"  principal.{attr} == false\n"
                f"}};"
            ),
        )

    def _baseline_to_constraints(self, controls: dict) -> list[CedarPolicy]:
        policies: list[CedarPolicy] = []

        max_tokens = controls.get("max_context_tokens")
        if max_tokens:
            policies.append(CedarPolicy(
                policy_id="pearl_baseline_max_tokens",
                description=f"Baseline: max context tokens = {max_tokens}",
                statement=(
                    f"forbid(\n"
                    f"  principal,\n"
                    f"  action == {self._ACTION_NS}::\"InvokeFoundationModel\",\n"
                    f"  resource\n"
                    f") when {{\n"
                    f"  context.request_token_count > {max_tokens}\n"
                    f"}};"
                ),
            ))

        allowed_models: list[str] = controls.get("allowed_model_ids") or []
        if allowed_models:
            model_set = ", ".join(f'"bedrock/{m}"' for m in allowed_models[:20])
            policies.append(CedarPolicy(
                policy_id="pearl_baseline_allowed_models",
                description="Baseline: restrict to approved model IDs",
                statement=(
                    f"forbid(\n"
                    f"  principal,\n"
                    f"  action == {self._ACTION_NS}::\"InvokeFoundationModel\",\n"
                    f"  resource\n"
                    f") unless {{\n"
                    f"  [{model_set}].contains(resource.model_id)\n"
                    f"}};"
                ),
            ))

        return policies
