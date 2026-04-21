# Dark Factory Governance

## Two Tracks: What Is Real Today vs. What Is Not

This document covers two distinct deployment realities. They are not on a continuum — they represent fundamentally different operating assumptions.

**Secure Agent Factories (implemented today):** Agent teams — coordinators, workers, evaluators — deployed in structured pipelines with human oversight at gate checkpoints. Agents know they are operating under PeaRL governance. They call PeaRL via MCP tools through LiteLLM. Humans approve promotion decisions at each gate. This is a real, working system.

**Secure Dark Agent Factories (aspirational / science fiction tier):** Fully autonomous lights-out factories where agent teams operate continuously without human intervention. No one is watching. Agents self-coordinate, self-deploy within governance bounds, and surface their own anomalies. This is not implemented today. It describes a target architecture and the governance primitives PeaRL would need to bound such a system if it existed.

The governance mechanisms described in this document are real PeaRL mechanisms. Their application to a fully autonomous lights-out factory is the aspirational part.

---

## Secure Agent Factories: Governance Summary

In Secure Agent Factories, PeaRL functions as the governance substrate for structured agent pipelines operating under human oversight.

**Agent teams** consist of coordinators (task orchestration), workers (deterministic computation), and evaluators (output scoring). Agents are registered as workloads via `pearl_register_agent_for_stage` before operating in any environment.

**Gate checkpoints** enforce policy before each promotion (`pilot → dev → preprod → prod`). Gate rules are evaluated deterministically — no model calls, no probabilistic logic. A gate either passes or blocks based on documented rule outcomes.

**Human approval** is required at every gate where `auto_pass=False`. Agents call `pearl_request_approval` to surface blocked actions to a human reviewer. Agents cannot approve their own promotions — `decideApproval` requires human reviewer role.

**MCP integration** routes all agent-to-PeaRL communication through LiteLLM proxy, which provides audit logging and spend control. Agents interact with PeaRL via 41 registered MCP tools covering workload registration, finding submission, approval requests, and factory run reporting.

Detailed documentation of the gate rule catalog, approval workflow, and MCP tool reference is maintained separately.

---

## Secure Dark Agent Factories: Governance Areas

The following sections describe the governance areas PeaRL targets for autonomous lights-out operation and the specific mechanisms that bound autonomous behavior. Where a mechanism is implemented today, it is described concretely. Where it is aspirational, this is stated explicitly.

---

### 1. Identity and Non-Human Identity (NHI)

In a lights-out factory, no human is present to verify that an agent is who it claims to be. Identity controls must be enforced structurally.

**PeaRL mechanisms:**

Every agent must be registered via `pearl_register_agent_for_stage` with an explicit role (`coordinator`, `worker`, `evaluator`) before it can operate in any stage. Registration records the agent's SVID (service identity), role, and associated allowance profile.

Gate rules evaluated at promotion:
- `NHI_IDENTITY_REGISTERED` — agent workload has a valid registration record
- `NHI_SECRETS_IN_VAULT` — credentials are stored in a secrets backend, not in environment variables or config files
- `NHI_CREDENTIAL_ROTATION_POLICY` — a rotation policy is documented and active
- `NHI_LEAST_PRIVILEGE_VERIFIED` — agent's effective permissions are scoped to its documented role
- `NHI_TOKEN_EXPIRY_CONFIGURED` — short-lived tokens are configured; no non-expiring credentials

**Kill switch:** `DELETE /workloads/{svid}` immediately removes an agent from the active workload registry. A deregistered agent cannot pass NHI gate checks and cannot be promoted to subsequent environments. This is a real API endpoint.

---

### 2. Capability Scoping (Allowance Profiles)

Autonomous agents must not be able to expand their own capabilities. Capability scope is defined at registration time and enforced at gate evaluation.

**PeaRL mechanisms:**

Agent Allowance Profiles define what tools, APIs, and data categories an agent is permitted to access. Profiles are versioned — each version records what changed and when. An agent operates under the allowance profile version that was active at its registration.

Gate rules:
- `AGENT_CAPABILITY_SCOPE_DOCUMENTED` — the agent's allowance profile is present and specifies permitted tools and APIs
- `AGENT_BLAST_RADIUS_ASSESSED` — the profile includes a documented assessment of what the agent can affect if it operates at full scope

**Kill switch:** Updating an allowance profile to remove capabilities takes effect on the next workload registration. An agent that re-registers after a profile update operates under the reduced scope. Agents cannot modify their own allowance profiles — profile management requires operator role.

---

### 3. Output and Blast Radius Control

A lights-out factory that can write to production without constraint is ungoverned. Output controls enforce read-only defaults and require explicit elevation for write access.

**PeaRL mechanisms:**

Gate rule `READ_ONLY_AUTONOMY` enforces that agents operating in production environments are restricted to read-only tool calls unless the gate has been explicitly evaluated and passed for write elevation. This is checked at promotion into the production environment.

Gate rule `AGENT_BLAST_RADIUS_ASSESSED` (also listed under capability scoping) requires that an agent's documented scope includes a clear statement of what it can write, delete, or modify — and that this has been reviewed.

**Kill switch:** Environment autonomy mode (`env_profile.autonomy_mode`) can be set to `read_only` at the environment level. When set, all agents operating in that environment are constrained to read-only tool access regardless of their allowance profile. This is an environment-level override, not an agent-level one.

*Note: `env_profile.autonomy_mode` as an enforced runtime constraint is partially implemented. The field exists; enforcement at the tool-call level in a fully autonomous factory is aspirational.*

---

### 4. Communication and Channel Security

In a lights-out factory, agent-to-agent and agent-to-tool communication happens without human observation. Communication security must be structural, not procedural.

**PeaRL mechanisms:**

All agent model calls and tool calls must route through LiteLLM proxy. This provides a single audit point for all inter-agent communication and enforces spend limits. Agents that bypass LiteLLM cannot be tracked and cannot have their behavior bounded.

Gate rules:
- `AGENT_COMMUNICATION_SECURED` — all agent communication routes through the designated proxy
- `OWASP_LLM05_IMPROPER_OUTPUT_HANDLING` — agent outputs are validated before being passed as inputs to downstream agents or tools
- `OWASP_LLM07_SYSTEM_PROMPT_LEAKAGE` — system prompts are not surfaced in agent outputs or logs

**Kill switch:** LiteLLM virtual key revocation immediately blocks all downstream model calls for the associated agent team. This is a hard cut — revoked keys cannot be used to make any model call, which effectively halts autonomous operation for that team without requiring agent-level deregistration.

---

### 5. Behavioral Drift Detection

An autonomous factory that operates for extended periods without human review can drift from its intended behavior. PeaRL provides a structured mechanism for surfacing drift without requiring real-time human observation.

**PeaRL mechanisms:**

Factory run summaries (`FactoryRunSummary`) are submitted by agent coordinators at the end of each factory run. Each summary aggregates per-run telemetry: models used, tools called, cost, duration, and any anomaly flags. Anomaly flags are sourced from open findings with categories `drift_acute`, `drift_trend`, or `behavioral_drift`.

Gate rule `FACTORY_RUN_SUMMARY_PRESENT` blocks promotion if the project has no factory run summary, or if the latest summary has open anomaly flags. This forces drift signals to be resolved before an agent team can advance to a higher-trust environment.

**Kill switch:** Creating a finding with category `drift_acute` and `status=open` immediately blocks the next gate evaluation for that project. A human (or a monitoring agent with appropriate role) can create this finding to halt promotion without requiring any other action. Resolving the finding (`status=resolved`) restores the promotion path.

*Note: Automated drift detection — where PeaRL itself identifies anomalous behavior and creates findings — is aspirational. Today, drift findings are submitted by agents or operators. The gate enforcement against open drift findings is implemented.*

---

### 6. Supply Chain and Model Governance

Autonomous factories consume models, packages, and external data. Supply chain integrity must be verified before production promotion.

**PeaRL mechanisms:**

Gate rules for supply chain and model governance:
- `SBOM_GENERATED` — a software bill of materials is present for the agent deployment
- `MODEL_CARD_DOCUMENTED` — a model card is present describing the model's intended use, limitations, and evaluation results
- `FAIRNESS_CASE_DEFINED` — a documented fairness assessment exists for the use case
- `AI_SCAN_COMPLETED` — a security scan has been completed via the MASS scanner integration
- `OWASP_LLM_TOP10_CLEAR` — all 10 OWASP LLM Top 10 v2025 categories have been assessed and addressed before production promotion

**Kill switch:** Any CRITICAL severity finding from the MASS scanner triggers the `CRITICAL_FINDINGS_ZERO` gate rule to fail. A single CRITICAL finding blocks all promotion to higher environments until the finding is resolved. This is enforced at gate evaluation time — no special action is required beyond the finding existing in an open state.

---

### 7. Promotion Sovereignty (the Final Kill Switch)

The most important governance control in any autonomous factory is the guarantee that autonomous agents cannot promote themselves. If this control fails, all other controls can be circumvented by an agent that promotes itself to an environment with fewer restrictions.

**PeaRL mechanisms:**

`decideApproval` requires human reviewer role. An agent calling this endpoint receives a 403. This is enforced at the API level — there is no configuration that allows an agent to approve its own promotion.

Gate evaluation is deterministic and model-free. PeaRL workers perform no LLM calls. A gate outcome cannot be influenced by prompting, jailbreaking, or any model-level manipulation. The gate either has documented passing evidence or it does not.

Trust accumulation gates can require N consecutive clean runs before auto-elevation is permitted. This means an agent team must demonstrate sustained compliant behavior across multiple factory runs before any gate can be set to `auto_pass=True`.

Setting `auto_pass=False` on any gate forces human approval regardless of gate rule outcomes. This is a per-gate configuration that cannot be overridden by an agent. Any gate can be pinned to require human review in perpetuity.

---

### 8. Emergency Stop

In a lights-out factory, the emergency stop must be operable by a single human action and must take effect immediately. PeaRL provides multiple independent emergency stop mechanisms at different scopes.

**Project-level stop (full halt):**

1. Deregister all workloads for the project via `DELETE /workloads/{svid}` for each registered agent. Removes all active agents from the workload registry. Agents cannot pass NHI gate checks after deregistration.

2. Set the project's `current_environment` back to `pilot`. Forces a full re-promotion cycle through all gates before any agent can reach a higher-trust environment.

3. Revoke the project's API key (`DELETE /users/api-keys/{key_id}`) or the associated LiteLLM virtual key. Severs all tool access and model call access simultaneously.

**Finding-based stop (targeted):**

Open a CRITICAL severity finding with `status=open` against the project. This immediately blocks all subsequent gate evaluations for that project via the `CRITICAL_FINDINGS_ZERO` rule. The project remains blocked until the finding is explicitly resolved by a human reviewer.

**Environment-level stop:**

Set `env_profile.autonomy_mode` to `read_only` for the target environment. Constrains all agents in that environment to read-only operations without requiring deregistration or key revocation.

These mechanisms are independent. Any one of them is sufficient to halt autonomous operation. Multiple mechanisms can be applied simultaneously for defense in depth.

---

## What PeaRL Does Not Provide

For completeness, the following are outside PeaRL's scope:

- **Runtime behavioral monitoring**: PeaRL evaluates gate rules at promotion time. It does not monitor agent behavior continuously during a factory run. Continuous behavioral monitoring would require a separate runtime observability system.
- **Automated remediation**: PeaRL blocks and surfaces. It does not automatically remediate findings or fix non-compliant configurations. Remediation is human-directed via `RemediationSpec`.
- **Model-level guardrails**: PeaRL is model-free. It does not inspect model inputs or outputs at inference time. Output validation (OWASP LLM05) is a gate rule requiring documented evidence, not a runtime filter.
- **Agent-to-agent authorization**: PeaRL governs agent-to-environment promotion. It does not currently govern which agents may call which other agents within a running factory. This is aspirational scope for LiteLLM-layer enforcement.
