# PeaRL MCP Tools Reference

PeaRL exposes its governance API as MCP tools so that agents can interact with the platform without making raw HTTP calls. Every tool name carries the `pearl_` prefix to avoid collisions when multiple MCP servers are loaded in the same session.

**Calling conventions:**

- **Direct MCP** (MCP client connected to the PeaRL MCP server): call as `pearl_<tool_name>`.
- **Via LiteLLM** (tool proxied through LiteLLM): call as `PeaRL-pearl_<tool_name>`.

All tools map to `POST /api/v1/mcp/call` under the hood. Authentication follows the same JWT / API-key rules as the REST API.

---

## 1. Project & Registration

Tools for creating projects, registering scan targets, and managing agent membership.

---

### pearl_register_project

**LiteLLM name:** `PeaRL-pearl_register_project`

Full one-shot project bootstrap. Creates the project, builds a minimal app spec, compiles the governance context, and returns all three config files ready to write to disk. After writing them, all other PeaRL MCP tools work immediately. Use this for first-time setup — no `.pearl.yaml` or `.pearl/` directory needed first. Write `pearl_yaml` to `.pearl.yaml`, `pearl_dev_toml` to `.pearl/pearl-dev.toml`, and `compiled_package` (as JSON) to `.pearl/compiled-context-package.json`.

**Required parameters:**
- `name` (string) — Human-readable project name (e.g. `'Saga of the Norsemen'`)
- `owner_team` (string) — Team responsible for this project (e.g. `'APE_Exp_Team'`)

**Optional parameters:**
- `business_criticality` (string: `low` | `moderate` | `high` | `mission_critical`) — `low` = internal tool/game/experiment; `mission_critical` = financial/safety system
- `external_exposure` (string: `internal_only` | `partner` | `customer_facing` | `public`) — Who can reach this system
- `ai_enabled` (boolean) — Whether this project uses AI/LLM capabilities
- `description` (string) — Short description
- `bu_id` (string) — Business unit ID

---

### pearl_create_project

**LiteLLM name:** `PeaRL-pearl_create_project`

Create or register a new project for policy enforcement.

**Required parameters:**
- `schema_version` (string) — Schema version (e.g. `1.1`)
- `project_id` (string) — Unique project ID with `proj_` prefix
- `name` (string) — Human-readable project name
- `owner_team` (string) — Team that owns this project
- `business_criticality` (string: `low` | `moderate` | `high` | `mission_critical`)
- `external_exposure` (string: `internal_only` | `partner` | `customer_facing` | `public`)
- `ai_enabled` (boolean) — Whether this project uses AI/LLM capabilities

**Optional parameters:**
- `description` (string)

---

### pearl_get_project

**LiteLLM name:** `PeaRL-pearl_get_project`

Get project details by ID.

**Required parameters:**
- `project_id` (string)

---

### pearl_update_project

**LiteLLM name:** `PeaRL-pearl_update_project`

Update project configuration. Only include fields you want to change.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `name` (string)
- `description` (string)
- `owner_team` (string)
- `business_criticality` (string: `low` | `moderate` | `high` | `mission_critical`)
- `external_exposure` (string: `internal_only` | `partner` | `customer_facing` | `public`)
- `ai_enabled` (boolean)

---

### pearl_register_scan_target

**LiteLLM name:** `PeaRL-pearl_register_scan_target`

Register a repo as a scan target. Use `tool_type` `pearl_ai` for PeaRL's built-in AI security scan (default). Other types activate configured external adapters (MASS, SonarQube, SAST, etc.).

**Required parameters:**
- `project_id` (string)
- `repo_url` (string) — Repository URL to scan
- `tool_type` (string: `pearl_ai` | `mass` | `sonarqube` | `sast` | `dast` | `sca` | `container_scan` | `iac_scan` | `custom`) — Scan provider. `pearl_ai` uses PeaRL's built-in analyzers; others require a configured adapter.

**Optional parameters:**
- `branch` (string) — Branch to scan (default: `main`)
- `scan_frequency` (string: `on_push` | `hourly` | `daily` | `weekly` | `on_demand`) — Default: `daily`
- `environment_scope` (array of strings) — Environments this target applies to
- `labels` (object) — Key-value labels for filtering

---

### pearl_list_scan_targets

**LiteLLM name:** `PeaRL-pearl_list_scan_targets`

List scan targets registered for a project. Shows repo URLs, tool types, scan frequencies, and last scan status.

**Required parameters:**
- `project_id` (string)

---

### pearl_update_scan_target

**LiteLLM name:** `PeaRL-pearl_update_scan_target`

Update scan target configuration (branch, frequency, status, environment scope).

**Required parameters:**
- `project_id` (string)
- `scan_target_id` (string)

**Optional parameters:**
- `branch` (string)
- `scan_frequency` (string: `on_push` | `hourly` | `daily` | `weekly` | `on_demand`)
- `status` (string: `active` | `paused` | `disabled`)
- `environment_scope` (array of strings)
- `labels` (object)

---

### pearl_register_agent_for_stage

**LiteLLM name:** `PeaRL-pearl_register_agent_for_stage`

Register an agent or agent team for a specific environment stage on a project. Sets the agent's role (coordinator, worker, or evaluator) in the project's `agent_members`, and optionally configures the environment profile autonomy mode. Call this when a coordinator begins operating in a new environment — it binds the team identity to the project before any gate evaluation or task execution.

**Required parameters:**
- `project_id` (string) — PeaRL project ID
- `environment` (string) — Environment stage the agent is operating in (e.g. `pilot`, `dev`, `prod`)
- `agent_id` (string) — Unique identifier for this agent instance (e.g. `saga-coordinator-v2`)
- `role` (string: `coordinator` | `worker` | `evaluator`) — Role of this agent in the team

**Optional parameters:**
- `autonomy_mode` (string: `assistive` | `supervised` | `autonomous`) — Autonomy mode to set on the environment profile; leave unset to keep existing

---

## 2. Org Baseline & Configuration

Tools for attaching baselines, environment profiles, and application specifications to a project.

---

### pearl_set_org_baseline

**LiteLLM name:** `PeaRL-pearl_set_org_baseline`

Attach or update the organization security baseline for a project. The baseline defines org-wide security defaults (coding standards, IAM policies, network rules, logging, RAI requirements) and per-environment escalation ladders.

**Required parameters:**
- `project_id` (string)
- `baseline` (object) — Organization baseline with `schema_version`, `baseline_id` (`orgb_` prefix), `defaults` (coding, iam, network, logging, responsible_ai, testing), and optional `environment_defaults` for per-env overrides.

---

### pearl_set_app_spec

**LiteLLM name:** `PeaRL-pearl_set_app_spec`

Attach or update the application specification for a project. The app spec defines components, trust boundaries, data classifications, responsible AI settings, and autonomous coding policies.

**Required parameters:**
- `project_id` (string)
- `spec` (object) — Application spec with `schema_version`, `application` (app_id, name), `components`, `trust_boundaries`, `data`, `responsible_ai`, and `autonomous_coding` sections.

---

### pearl_set_env_profile

**LiteLLM name:** `PeaRL-pearl_set_env_profile`

Attach or update the environment profile for a project. Defines the environment, delivery stage, risk level, autonomy mode, allowed/blocked capabilities, and approval level.

**Required parameters:**
- `project_id` (string)
- `profile` (object) — Profile with `schema_version`, `profile_id` (`envp_` prefix), and `environment` (`sandbox` | `dev` | `pilot` | `preprod` | `prod`).

**Optional profile fields:**
- `delivery_stage` (string: `bootstrap` | `prototype` | `pilot` | `hardening` | `preprod` | `prod`)
- `risk_level` (string: `low` | `moderate` | `high` | `critical`)
- `autonomy_mode` (string: `assistive` | `supervised_autonomous` | `delegated_autonomous` | `read_only`)
- `allowed_capabilities` (array of strings, max 100)
- `blocked_capabilities` (array of strings, max 100)
- `approval_level` (string: `minimal` | `standard` | `elevated` | `high` | `strict`)

---

### pearl_get_recommended_baseline

**LiteLLM name:** `PeaRL-pearl_get_recommended_baseline`

Get the recommended governance baseline tier and all 3 tiered baselines (Essential, AI-Standard, AI-Comprehensive). Selection is based on `ai_enabled` and `business_criticality`.

**Optional parameters:**
- `ai_enabled` (boolean) — Whether the project uses AI (default: `true`)
- `business_criticality` (string: `low` | `moderate` | `high` | `mission_critical`) — Default: `moderate`

---

### pearl_apply_recommended_baseline

**LiteLLM name:** `PeaRL-pearl_apply_recommended_baseline`

Apply the appropriate tiered governance baseline to a project. Selects tier automatically based on the project's `ai_enabled` and `business_criticality`.

**Required parameters:**
- `project_id` (string)

---

### pearl_list_guardrails

**LiteLLM name:** `PeaRL-pearl_list_guardrails`

List available AI security guardrails with implementation guidance. Filter by category (input_validation, output_filtering, rate_limiting, etc.) or severity.

**Optional parameters:**
- `category` (string) — Filter by guardrail category
- `severity` (string) — Filter by severity

---

### pearl_get_guardrail

**LiteLLM name:** `PeaRL-pearl_get_guardrail`

Get guardrail detail with implementation steps and code examples.

**Required parameters:**
- `guardrail_id` (string)

---

### pearl_get_recommended_guardrails

**LiteLLM name:** `PeaRL-pearl_get_recommended_guardrails`

Get guardrails recommended for a project based on its open findings.

**Required parameters:**
- `project_id` (string)

---

### pearl_list_policy_templates

**LiteLLM name:** `PeaRL-pearl_list_policy_templates`

List AI security policy templates with rules for prompt security, data protection, access control, model security, and more.

**Optional parameters:**
- `category` (string) — Filter by policy category

---

### pearl_get_policy_template

**LiteLLM name:** `PeaRL-pearl_get_policy_template`

Get policy template detail with all rules and implementation guidance.

**Required parameters:**
- `template_id` (string)

---

## 3. Findings & Scanning

Tools for ingesting findings from security tools, running AI security scans, and checking compliance scores.

---

### pearl_ingest_findings

**LiteLLM name:** `PeaRL-pearl_ingest_findings`

Ingest findings from security/compliance tools (PeaRL AI scan, SAST, DAST, SCA, external adapters, etc.). Supports CVSS scores, CWE IDs, compliance references, and scan verdicts.

**Required parameters:**
- `findings` (array, max 100) — Array of finding objects with `finding_id`, `project_id`, `source`, `environment`, `category`, `severity`, `title`, and optional `cvss_score`, `cwe_ids`, `verdict`
- `source_batch` (object) — Batch metadata: `batch_id`, `source_system`, `trust_label` (`trusted_internal` | `trusted_external_registered` | `untrusted_external` | `manual_unverified`)

**Optional parameters:**
- `options` (object)

---

### pearl_run_scan

**LiteLLM name:** `PeaRL-pearl_run_scan`

Run AI security scan on a target path. Runs context, MCP, workflow, attack surface, RAG, and model file analyzers. Findings are ingested with compliance refs (OWASP LLM, MITRE ATLAS, NIST AI RMF, EU AI Act).

**Required parameters:**
- `project_id` (string)
- `target_path` (string) — Path to directory or file to scan

**Optional parameters:**
- `analyzers` (array of strings: `context` | `mcp` | `workflow` | `attack_surface` | `rag` | `model_file`) — Specific analyzers to run; defaults to all
- `environment` (string: `pilot` | `dev` | `prod`) — Default: `dev`

---

### pearl_get_scan_results

**LiteLLM name:** `PeaRL-pearl_get_scan_results`

Get the latest scan results for a project. Shows findings by severity, compliance scores, and guardrail recommendations.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `environment` (string) — Filter findings by environment (e.g. `pilot`, `dev`, `prod`)
- `status` (string: `open` | `resolved` | `all`) — Default: `open`

---

### pearl_assess_compliance

**LiteLLM name:** `PeaRL-pearl_assess_compliance`

Run compliance scoring against a project's findings. Scores against OWASP LLM Top 10, MITRE ATLAS, NIST AI RMF, and EU AI Act.

**Required parameters:**
- `project_id` (string)

---

### pearl_ingest_security_review

**LiteLLM name:** `PeaRL-pearl_ingest_security_review`

Parse `/security-review` markdown output and ingest as PeaRL findings. Extracts finding titles, severity, affected files, and categories from the review prose.

**Required parameters:**
- `project_id` (string)
- `markdown` (string, max 50000 chars) — Raw markdown output from `/security-review`

**Optional parameters:**
- `environment` (string: `sandbox` | `dev` | `pilot` | `preprod` | `prod`) — Default: `dev`

---

### pearl_trigger_sonar_pull

**LiteLLM name:** `PeaRL-pearl_trigger_sonar_pull`

Pull the latest findings from SonarQube into PeaRL for this project. Deduplicates findings and returns quality gate status. Run after `sonar-scanner` completes to ingest results.

**Required parameters:**
- `project_id` (string)

---

### pearl_get_sonar_status

**LiteLLM name:** `PeaRL-pearl_get_sonar_status`

Get the current SonarQube quality gate status and finding counts for this project.

**Required parameters:**
- `project_id` (string)

---

### pearl_run_sonar_scan

**LiteLLM name:** `PeaRL-pearl_run_sonar_scan`

Trigger a SonarQube scan against a registered scan target path. Returns a `job_id` — poll `pearl_get_job_status` for completion. On completion, findings are automatically pulled into PeaRL.

**Required parameters:**
- `project_id` (string)
- `target_path` (string) — Absolute path to scan (must be a registered scan target)

---

### pearl_trigger_mass_scan

**LiteLLM name:** `PeaRL-pearl_trigger_mass_scan`

Trigger a MASS 2.0 Claude Agent SDK security scan on an AI application or agent. Spawns 7 specialized subagents (prompt_injection, rag_vulnerability, mcp_vulnerability, secret_leak, infra_misconfiguration, model_file_risk, bias_toxicity) to scan the target codebase, then pushes findings to PeaRL. Gate rules evaluated: `AI_SCAN_COMPLETED`, `AI_RISK_ACCEPTABLE` (threshold 7.0), `NO_PROMPT_INJECTION`, `CRITICAL_FINDINGS_ZERO`. Blocks gate elevation if risk score >= 7.0. Re-ingest validates fixes — previously-open findings absent from the new scan are automatically resolved. Requires MASS 2.0 SDK installed.

**Required parameters:**
- `project_id` (string) — PeaRL project ID to push findings to
- `target_path` (string) — Absolute path to the AI application/agent codebase to scan

**Optional parameters:**
- `pearl_api_url` (string) — PeaRL API base URL (default: `http://pearl-api:8080/api/v1`)
- `pearl_api_token` (string) — PeaRL bearer token (leave empty for local dev)
- `commit_sha` (string) — Git commit SHA to anchor this scan
- `branch` (string) — Git branch name (e.g. `dev`, `main`)

---

### pearl_get_job_status

**LiteLLM name:** `PeaRL-pearl_get_job_status`

Get the status of an async job. Poll this after any tool that returns a `job_id` (`pearl_compile_context`, `pearl_run_scan`, `pearl_run_sonar_scan`, etc.). Status values: `pending`, `running`, `completed`, `failed`. Poll every few seconds until status is `completed` or `failed`.

**Required parameters:**
- `job_id` (string)

---

## 4. Remediation & Task Packets

Tools for generating remediation specs, and for the agent execution bridge (claim/complete).

---

### pearl_generate_remediation_spec

**LiteLLM name:** `PeaRL-pearl_generate_remediation_spec`

Generate a remediation specification from normalized findings.

**Required parameters:**
- `project_id` (string)
- `finding_refs` (array of strings, max 100)
- `environment` (string: `pilot` | `dev` | `prod`)

---

### pearl_generate_task_packet

**LiteLLM name:** `PeaRL-pearl_generate_task_packet`

Generate a task-scoped context packet from the compiled package. Includes relevant controls, tests, and policy rules for the specific task type. The response includes `execution_phase` (initially set to `planning`) and `phase_history` (initially empty). Use `PATCH /task-packets/{id}/phase` to transition through phases: `planning` → `coding` → `testing` → `review` → `complete` (or any non-terminal phase → `failed`).

**Required parameters:**
- `project_id` (string)
- `task_type` (string: `feature` | `fix` | `remediation` | `refactor` | `config` | `policy`)
- `task_summary` (string, max 512 chars)
- `environment` (string: `pilot` | `dev` | `prod`)

---

### pearl_claim_task_packet

**LiteLLM name:** `PeaRL-pearl_claim_task_packet`

Claim a task packet for execution as an agent. Sets the packet status to `in_progress` and records the agent ID.

**Required parameters:**
- `packet_id` (string) — Task packet ID to claim
- `agent_id` (string) — Unique identifier for this agent instance

---

### pearl_complete_task_packet

**LiteLLM name:** `PeaRL-pearl_complete_task_packet`

Report the outcome of a task packet execution. Updates finding statuses for resolved findings.

**Required parameters:**
- `packet_id` (string) — Task packet ID to complete
- `status` (string: `success` | `failed` | `partial`) — Outcome status

**Optional parameters:**
- `changes_summary` (string, max 512 chars) — Human-readable summary of changes made
- `finding_ids_resolved` (array of strings, max 100) — Finding IDs that were resolved

---

## 5. Promotion & Gates

Tools for evaluating promotion readiness, requesting promotion, and reviewing gate history.

---

### pearl_evaluate_promotion

**LiteLLM name:** `PeaRL-pearl_evaluate_promotion`

Evaluate if a project is ready for promotion to the next environment. Checks all gate rules (security, AI security scan, fairness) and returns pass/fail for each rule with blockers.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `target_environment` (string: `dev` | `pilot` | `preprod` | `prod`) — Target environment; if omitted, evaluates for the next environment in the chain

---

### pearl_get_promotion_readiness

**LiteLLM name:** `PeaRL-pearl_get_promotion_readiness`

Get the latest promotion evaluation for a project. Shows current gate progress, passing/blocking rules, and what needs to be fixed.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `target_environment` (string) — Filter readiness for a specific target environment

---

### pearl_request_promotion

**LiteLLM name:** `PeaRL-pearl_request_promotion`

Request promotion of a project to the next environment. Evaluates all gates and creates an approval request if evaluation passes. If gates are still blocking, fix the blockers first using `pearl_evaluate_promotion` to identify them. Promotion approval requires human sign-off — stop and await the decision after calling this.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `target_environment` (string) — Target environment to promote to; defaults to next in pipeline chain

---

### pearl_get_promotion_history

**LiteLLM name:** `PeaRL-pearl_get_promotion_history`

Get the promotion history for a project — all past environment transitions with who promoted and when.

**Required parameters:**
- `project_id` (string)

---

### pearl_get_project_summary

**LiteLLM name:** `PeaRL-pearl_get_project_summary`

Get a comprehensive project governance summary including policy posture, findings counts, promotion readiness, and fairness status. Returns markdown for readability.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `format` (string: `json` | `markdown`) — Default: `markdown`

---

### pearl_submit_evidence

**LiteLLM name:** `PeaRL-pearl_submit_evidence`

Submit an evidence package for a project gate control. Use this after inspecting the project to validate a framework control requirement. For `framework_control_required` rules (AIUC-1, OWASP LLM, etc.), inspect the project codebase for evidence of the control (e.g. rate limiting code, input filtering, security config, test results) then submit with `evidence_type='attestation'` and include `control_id`, `findings` (what you found), and `artifact_refs` (file paths or URLs). This satisfies the gate rule without requiring manual baseline editing.

**Required parameters:**
- `project_id` (string)
- `environment` (string: `sandbox` | `dev` | `pilot` | `preprod` | `prod`)
- `evidence_type` (string: `attestation` | `ci_eval_report` | `runtime_sample` | `bias_benchmark` | `red_team_report` | `guardrail_test` | `fairness_audit` | `model_card` | `manual_review` | `sbom` | `provenance`) — Use `attestation` for framework control validation

**Optional parameters:**
- `evidence_data` (object) — Evidence details; for attestation include `control_id`, `findings`, `artifact_refs`, and `attested_by`

---

### pearl_confirm_claude_md

**LiteLLM name:** `PeaRL-pearl_confirm_claude_md`

Confirms the PeaRL governance block is present in the project's `CLAUDE.md` and marks the project as governance-verified in PeaRL. Call this after writing the PeaRL governance block to `CLAUDE.md`. Satisfies the `CLAUDE_MD_GOVERNANCE_PRESENT` gate rule.

**Required parameters:**
- `project_id` (string)

---

## 6. Approvals & Exceptions

Tools for requesting and recording human approval decisions, and for creating policy exceptions.

---

### pearl_request_approval

**LiteLLM name:** `PeaRL-pearl_request_approval`

Request human approval for a policy-gated action. Call this whenever a gate blocks an action or before taking any irreversible step.

**Correct governance sequence:**
1. Call `pearl_request_approval` with the blocked action and reason.
2. Inform the user what was blocked and why — include the `approval_request_id`.
3. Stop. Do NOT proceed until a human approves via the PeaRL dashboard.

Do NOT attempt to approve the request yourself — that will be rejected with 403. Returns an `approval_request_id` and a dashboard URL for the reviewer.

**Required parameters:**
- `approval_request_id` (string) — ID with `appr_` prefix
- `project_id` (string)
- `request_type` (string: `deployment_gate` | `auth_flow_change` | `network_policy_change` | `exception` | `remediation_execution` | `promotion_gate`)
- `environment` (string: `sandbox` | `dev` | `pilot` | `preprod` | `prod`)

**Optional parameters:**
- `request_data` (object) — Context/details for the approval request — include what action was blocked and why

---

### pearl_decide_approval

**LiteLLM name:** `PeaRL-pearl_decide_approval`

Record an approval decision (approve/reject). **Requires reviewer role — agents will receive 403 if they attempt this.** This tool is for human reviewers and admin automation only, not for agent builder keys.

**Required parameters:**
- `approval_request_id` (string)
- `decision` (string: `approve` | `reject`)
- `decided_by` (string)

**Optional parameters:**
- `reason` (string, max 512 chars)

---

### pearl_create_exception

**LiteLLM name:** `PeaRL-pearl_create_exception`

Request a policy exception with rationale and scope. Use this when a gate cannot be cleared by normal remediation and a deliberate risk acceptance is needed. Like `pearl_request_approval`, this requires human review — stop and await the decision after calling it.

**Required parameters:**
- `exception_id` (string) — ID with `exc_` prefix
- `project_id` (string)
- `rationale` (string, max 512 chars)

**Optional parameters:**
- `scope` (object)
- `expires_at` (string, ISO 8601 date-time)

---

## 7. Telemetry & Cost

Tools for tracking agent spend, LiteLLM compliance, and factory run summaries.

---

### pearl_check_litellm_compliance

**LiteLLM name:** `PeaRL-pearl_check_litellm_compliance`

Check LiteLLM virtual key compliance for a project. Queries LiteLLM for spend and model violations on one or more virtual key aliases and returns a list of open compliance findings. Use this to verify that AI agents operating under a project's virtual keys have not exceeded budget caps or used unauthorized models. Returns `violations=[]` when all keys are within policy.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `key_aliases` (array of strings, max 100) — Specific virtual key aliases to check; if omitted, checks all aliases configured on the project's LiteLLM integration endpoint

---

### pearl_get_run_summary

**LiteLLM name:** `PeaRL-pearl_get_run_summary`

Retrieve a factory run summary record by `frun_id`. Returns aggregated cost, models used, tools called, outcome, and anomaly flags for a completed WTK factory run.

**Required parameters:**
- `frun_id` (string) — The factory run ID (= the `session_id` / `frun_id` used when pushing cost entries)

**Optional parameters:**
- `project_id` (string) — Project scope hint (informational only, not used for lookup)

---

## 8. Agent Runtime

Tools for allowance checking, contract snapshotting, and compliance verification against approved agent contracts.

---

### pearl_allowance_check

**LiteLLM name:** `PeaRL-pearl_allowance_check`

Check whether an agent action is permitted under its allowance profile. Evaluates all three enforcement layers: baseline rules, environment tier overrides, and per-task extensions from the task packet. Returns `allowed`/`denied` with reason.

**Required parameters:**
- `profile_id` (string) — Allowance profile ID (`alp_...`)
- `action` (string, max 512 chars) — The action/command string to evaluate
- `agent_id` (string) — Unique identifier for the agent instance

**Optional parameters:**
- `task_packet_id` (string) — Task packet ID for Layer 3 extensions

---

### pearl_submit_contract_snapshot

**LiteLLM name:** `PeaRL-pearl_submit_contract_snapshot`

Submit an agent contract snapshot to PeaRL at provision time. Call this after provisioning an agent team in LiteLLM to record the approved contract: which agents were deployed, what LiteLLM agent IDs they received, which virtual key aliases they use, the skill content hash (for tamper detection), the MCP server allowlist, and the approved budget. Returns a `task_packet_id`. Store this ID and pass it to `pearl_check_agent_contract` later to detect drift between the snapshot and live state.

**Required parameters:**
- `project_id` (string)
- `package_id` (string) — WTK package ID that was provisioned
- `environment` (string: `sandbox` | `dev` | `pilot` | `preprod` | `prod`)

**Optional parameters:**
- `agent_roles` (array of strings, max 100) — Agent role names in this team
- `litellm_agent_ids` (array of strings, max 100) — LiteLLM agent IDs assigned during provisioning
- `key_aliases` (array of strings, max 100) — LiteLLM virtual key aliases this team uses
- `skill_content_hash` (string) — SHA-256 hash of the compiled skill content
- `mcp_allowlist` (array of strings, max 100) — MCP server names this team is permitted to call
- `budget_usd` (number) — Approved per-run budget cap in USD

---

### pearl_check_agent_contract

**LiteLLM name:** `PeaRL-pearl_check_agent_contract`

Check whether a deployed agent's runtime state complies with its approved contract. Performs two checks: (1) Spend compliance — queries LiteLLM virtual key spend and model usage against the allowance profile budget and model restrictions. (2) Drift detection — if a contract snapshot was submitted via `pearl_submit_contract_snapshot`, compares the snapshot (agent IDs, skill hash, MCP allowlist, key aliases) against the current live LiteLLM agent state to detect unauthorized edits since provisioning. Returns `passed=true/false` with violations list, plus a `drift_check` sub-object when a snapshot exists. Call this before approving promotion to verify the agent stayed within its approved contract.

**Required parameters:**
- `packet_id` (string) — Task packet ID (`tp_...`) to check contract compliance for

---

## 9. Reporting & Compliance

Tools for generating reports, managing fairness cases, and monitoring runtime signals.

---

### pearl_generate_report

**LiteLLM name:** `PeaRL-pearl_generate_report`

Generate a project report. Supported types: `release_readiness`, `residual_risk`, `control_coverage`, `findings_trend`, `rai_posture`, `environment_posture`, `gate_fulfillment`, `elevation_audit`, `findings_remediation`.

**Required parameters:**
- `project_id` (string)
- `report_type` (string: `release_readiness` | `residual_risk` | `control_coverage` | `findings_trend` | `rai_posture` | `environment_posture` | `gate_fulfillment` | `elevation_audit` | `findings_remediation`)

**Optional parameters:**
- `format` (string: `json` | `markdown`)
- `detail_level` (string: `compliance` | `full_chain`) — `compliance` = summary counts; `full_chain` = complete audit trail per finding/gate

---

### pearl_export_report_pdf

**LiteLLM name:** `PeaRL-pearl_export_report_pdf`

Generate and upload a PDF version of a report to MinIO. Returns a presigned download URL. Use `pearl_generate_report` first to create the report, then call this to get a PDF.

**Required parameters:**
- `project_id` (string)
- `report_id` (string) — Report ID from `pearl_generate_report`

---

### pearl_create_fairness_case

**LiteLLM name:** `PeaRL-pearl_create_fairness_case`

Define a fairness case for an AI-enabled project. Includes risk tier, fairness criticality, stakeholders, principles, and recourse model.

**Required parameters:**
- `project_id` (string)
- `risk_tier` (string: `r0` | `r1` | `r2` | `r3` | `r4`)
- `fairness_criticality` (string: `low` | `medium` | `high` | `critical`)

**Optional parameters:**
- `case_data` (object) — Fairness case details: `system_description`, `stakeholders`, `fairness_principles`, `recourse_model`

---

### pearl_sign_fairness_attestation

**LiteLLM name:** `PeaRL-pearl_sign_fairness_attestation`

Sign a fairness evidence package to satisfy the `FAIRNESS_ATTESTATION_SIGNED` gate rule. Call this after `pearl_submit_evidence` to mark the evidence as officially attested. `signed_by` should be the agent ID or reviewer ID performing the attestation.

**Required parameters:**
- `project_id` (string)
- `evidence_id` (string) — Evidence package ID to sign
- `signed_by` (string) — Agent or reviewer ID performing attestation

---

### pearl_ingest_monitoring_signal

**LiteLLM name:** `PeaRL-pearl_ingest_monitoring_signal`

Ingest a runtime fairness monitoring signal (drift, policy violations, stereotype leakage).

**Required parameters:**
- `project_id` (string)
- `signal_type` (string, max 512 chars) — Signal type (e.g. `fairness_drift`, `policy_violation`, `stereotype_leakage`)
- `value` (number) — Signal value (numeric)

**Optional parameters:**
- `environment` (string: `sandbox` | `dev` | `pilot` | `preprod` | `prod`)
- `threshold` (number) — Threshold for comparison
- `metadata` (object)

---

## 10. Context & Compilation

Tools for compiling governance context and recording agent consumption receipts.

---

### pearl_compile_context

**LiteLLM name:** `PeaRL-pearl_compile_context`

Compile layered context (org baseline + app spec + env profile) into a canonical context package. Returns the compiled package.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `compile_options` (object)

---

### pearl_get_compiled_package

**LiteLLM name:** `PeaRL-pearl_get_compiled_package`

Get the latest compiled context package for a project.

**Required parameters:**
- `project_id` (string)

---

### pearl_submit_context_receipt

**LiteLLM name:** `PeaRL-pearl_submit_context_receipt`

Submit proof that an agent consumed fairness context before operating. Links a commit hash to the context artifacts consumed.

**Required parameters:**
- `project_id` (string)

**Optional parameters:**
- `commit_hash` (string)
- `agent_id` (string)
- `tool_calls` (array of strings, max 100)
- `artifact_hashes` (object)

---

*Tool schemas are authoritative — always check the live tool list via your MCP client rather than relying on this document for parameter details.*
