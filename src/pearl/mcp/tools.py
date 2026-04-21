"""MCP tool definitions mapping to PeaRL API operations.

55 tools total. All tool names use the pearl_ prefix so agents can
unambiguously distinguish PeaRL tools when multiple MCP servers are loaded.
"""

TOOL_DEFINITIONS = [
    # ─── Project Management ──────────────────────────
    {
        "name": "pearl_register_project",
        "description": (
            "Full one-shot project bootstrap. "
            "Creates the project, builds a minimal app spec, compiles the governance context, "
            "and returns all three config files ready to write to disk. "
            "After writing them, all other PeaRL MCP tools work immediately. "
            "Use this for first-time setup — no .pearl.yaml or .pearl/ directory needed first. "
            "Write pearl_yaml to .pearl.yaml, pearl_dev_toml to .pearl/pearl-dev.toml, "
            "and compiled_package (as JSON) to .pearl/compiled-context-package.json."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 512, "description": "Human-readable project name (e.g. 'Saga of the Norsemen')"},
                "owner_team": {"type": "string", "maxLength": 512, "description": "Team responsible for this project (e.g. 'APE_Exp_Team')"},
                "business_criticality": {
                    "type": "string",
                    "enum": ["low", "moderate", "high", "mission_critical"],
                    "default": "low",
                    "description": "low = internal tool/game/experiment; mission_critical = financial/safety system",
                },
                "external_exposure": {
                    "type": "string",
                    "enum": ["internal_only", "partner", "customer_facing", "public"],
                    "default": "public",
                    "description": "Who can reach this system",
                },
                "ai_enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether this project uses AI/LLM capabilities",
                },
                "description": {"type": "string", "maxLength": 512, "description": "Optional short description"},
                "bu_id": {"type": "string", "maxLength": 512, "description": "Optional business unit ID"},
            },
            "required": ["name", "owner_team"],
        },
    },
    {
        "name": "pearl_create_project",
        "description": "Create or register a new project for policy enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "minLength": 1, "pattern": r"^\d+\.\d+(\.\d+)?$", "default": "1.1"},
                "project_id": {"type": "string", "minLength": 1, "pattern": "^proj_[A-Za-z0-9_-]+$", "description": "Unique project ID (prefix: proj_)"},
                "name": {"type": "string", "maxLength": 512, "description": "Human-readable project name"},
                "description": {"type": "string", "maxLength": 512},
                "owner_team": {"type": "string", "maxLength": 512, "description": "Team that owns this project"},
                "business_criticality": {"type": "string", "enum": ["low", "moderate", "high", "mission_critical"]},
                "external_exposure": {"type": "string", "enum": ["internal_only", "partner", "customer_facing", "public"]},
                "ai_enabled": {"type": "boolean", "description": "Whether this project uses AI/LLM capabilities"},
            },
            "required": ["schema_version", "project_id", "name", "owner_team", "business_criticality", "external_exposure", "ai_enabled"],
        },
    },
    {
        "name": "pearl_get_project",
        "description": "Get project details by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_update_project",
        "description": "Update project configuration. Only include fields you want to change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string", "maxLength": 512},
                "description": {"type": "string", "maxLength": 512},
                "owner_team": {"type": "string", "maxLength": 512},
                "business_criticality": {"type": "string", "enum": ["low", "moderate", "high", "mission_critical"]},
                "external_exposure": {"type": "string", "enum": ["internal_only", "partner", "customer_facing", "public"]},
                "ai_enabled": {"type": "boolean"},
            },
            "required": ["project_id"],
        },
    },

    # ─── Project Configuration ───────────────────────
    {
        "name": "pearl_set_org_baseline",
        "description": "Attach or update the organization security baseline for a project. The baseline defines org-wide security defaults (coding standards, IAM policies, network rules, logging, RAI requirements) and per-environment escalation ladders.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "baseline": {
                    "type": "object",
                    "description": "Organization baseline with schema_version, baseline_id, defaults (coding, iam, network, logging, responsible_ai, testing), and optional environment_defaults for per-env overrides.",
                    "properties": {
                        "schema_version": {"type": "string", "default": "1.1"},
                        "baseline_id": {"type": "string", "minLength": 1, "pattern": "^orgb_[A-Za-z0-9_-]+$"},
                        "defaults": {"type": "object"},
                        "environment_defaults": {"type": "object"},
                    },
                    "required": ["schema_version", "baseline_id", "defaults"],
                },
            },
            "required": ["project_id", "baseline"],
        },
    },
    {
        "name": "pearl_set_app_spec",
        "description": "Attach or update the application specification for a project. The app spec defines components, trust boundaries, data classifications, responsible AI settings, and autonomous coding policies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "spec": {
                    "type": "object",
                    "description": "Application spec with schema_version, application (app_id, name), components, trust_boundaries, data, responsible_ai, and autonomous_coding sections.",
                    "properties": {
                        "schema_version": {"type": "string", "default": "1.1"},
                        "application": {"type": "object"},
                        "components": {"type": "array", "maxItems": 100},
                        "trust_boundaries": {"type": "array", "maxItems": 100},
                        "data": {"type": "object"},
                    },
                    "required": ["schema_version"],
                },
            },
            "required": ["project_id", "spec"],
        },
    },
    {
        "name": "pearl_set_env_profile",
        "description": "Attach or update the environment profile for a project. Defines the environment, delivery stage, risk level, autonomy mode, allowed/blocked capabilities, and approval level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "profile": {
                    "type": "object",
                    "properties": {
                        "schema_version": {"type": "string", "default": "1.1"},
                        "profile_id": {"type": "string", "minLength": 1, "pattern": "^envp_[A-Za-z0-9_-]+$"},
                        "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                        "delivery_stage": {"type": "string", "enum": ["bootstrap", "prototype", "pilot", "hardening", "preprod", "prod"]},
                        "risk_level": {"type": "string", "enum": ["low", "moderate", "high", "critical"]},
                        "autonomy_mode": {"type": "string", "enum": ["assistive", "supervised_autonomous", "delegated_autonomous", "read_only"]},
                        "allowed_capabilities": {"type": "array", "maxItems": 100, "items": {"type": "string"}},
                        "blocked_capabilities": {"type": "array", "maxItems": 100, "items": {"type": "string"}},
                        "approval_level": {"type": "string", "enum": ["minimal", "standard", "elevated", "high", "strict"]},
                    },
                    "required": ["schema_version", "profile_id", "environment"],
                },
            },
            "required": ["project_id", "profile"],
        },
    },

    # ─── Context Compilation ─────────────────────────
    {
        "name": "pearl_compile_context",
        "description": "Compile layered context (org baseline + app spec + env profile) into a canonical context package. Returns the compiled package.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "compile_options": {"type": "object"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_get_compiled_package",
        "description": "Get the latest compiled context package for a project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_generate_task_packet",
        "description": (
            "Generate a task-scoped context packet from the compiled package. "
            "Includes relevant controls, tests, and policy rules for the specific task type. "
            "The response includes execution_phase (initially set to 'planning') and phase_history (initially empty). "
            "Use PATCH /task-packets/{id}/phase to transition through phases: "
            "planning → coding → testing → review → complete (or any non-terminal phase → failed)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_type": {"type": "string", "enum": ["feature", "fix", "remediation", "refactor", "config", "policy"]},
                "task_summary": {"type": "string", "maxLength": 512},
                "environment": {"type": "string", "enum": ["pilot", "dev", "prod"]},
            },
            "required": ["project_id", "task_type", "task_summary", "environment"],
        },
    },

    # ─── Findings ────────────────────────────────────
    {
        "name": "pearl_ingest_findings",
        "description": "Ingest findings from security/compliance tools (PeaRL AI scan, SAST, DAST, SCA, external adapters, etc.). Supports CVSS scores, CWE IDs, compliance references, and scan verdicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "findings": {"type": "array", "maxItems": 100, "description": "Array of finding objects with finding_id, project_id, source, environment, category, severity, title, and optional cvss_score, cwe_ids, verdict"},
                "source_batch": {
                    "type": "object",
                    "properties": {
                        "batch_id": {"type": "string"},
                        "source_system": {"type": "string"},
                        "trust_label": {"type": "string", "enum": ["trusted_internal", "trusted_external_registered", "untrusted_external", "manual_unverified"]},
                    },
                    "required": ["batch_id", "source_system", "trust_label"],
                },
                "options": {"type": "object"},
            },
            "required": ["findings", "source_batch"],
        },
    },
    {
        "name": "pearl_generate_remediation_spec",
        "description": "Generate a remediation specification from normalized findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "finding_refs": {"type": "array", "maxItems": 100, "items": {"type": "string"}},
                "environment": {"type": "string", "enum": ["pilot", "dev", "prod"]},
            },
            "required": ["project_id", "finding_refs", "environment"],
        },
    },

    # ─── Approvals & Exceptions ──────────────────────
    {
        "name": "pearl_request_approval",
        "description": (
            "Request human approval for a policy-gated action. "
            "Call this whenever a gate blocks an action or before taking any irreversible step. "
            "Correct governance sequence: "
            "1) Call pearl_request_approval with the blocked action and reason. "
            "2) Inform the user what was blocked and why — include the approval_request_id. "
            "3) Stop. Do NOT proceed until a human approves via the PeaRL dashboard. "
            "Do NOT attempt to approve the request yourself — that will be rejected with 403. "
            "Returns an approval_request_id and a dashboard URL for the reviewer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "approval_request_id": {"type": "string", "minLength": 1, "pattern": "^appr_[A-Za-z0-9_-]+$"},
                "project_id": {"type": "string"},
                "request_type": {"type": "string", "enum": ["deployment_gate", "auth_flow_change", "network_policy_change", "exception", "remediation_execution", "promotion_gate"]},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "request_data": {"type": "object", "description": "Context/details for the approval request — include what action was blocked and why"},
            },
            "required": ["approval_request_id", "project_id", "request_type", "environment"],
        },
    },
    {
        "name": "pearl_decide_approval",
        "description": (
            "Record an approval decision (approve/reject). "
            "REQUIRES reviewer role — agents will receive 403 if they attempt this. "
            "This tool is for human reviewers and admin automation only, not for agent builder keys."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "approval_request_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
                "decided_by": {"type": "string"},
                "reason": {"type": "string", "maxLength": 512},
            },
            "required": ["approval_request_id", "decision", "decided_by"],
        },
    },
    {
        "name": "pearl_create_exception",
        "description": (
            "Request a policy exception with rationale and scope. "
            "Use this when a gate cannot be cleared by normal remediation and a deliberate risk acceptance is needed. "
            "Like pearl_request_approval, this requires human review — stop and await the decision after calling it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "exception_id": {"type": "string", "minLength": 1, "pattern": "^exc_[A-Za-z0-9_-]+$"},
                "project_id": {"type": "string"},
                "rationale": {"type": "string", "maxLength": 512},
                "scope": {"type": "object"},
                "expires_at": {"type": "string", "format": "date-time"},
            },
            "required": ["exception_id", "project_id", "rationale"],
        },
    },

    # ─── Reports ─────────────────────────────────────
    {
        "name": "pearl_generate_report",
        "description": "Generate a project report (release_readiness, residual_risk, control_coverage, findings_trend, rai_posture, environment_posture, gate_fulfillment, elevation_audit, findings_remediation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "report_type": {"type": "string", "enum": ["release_readiness", "residual_risk", "control_coverage", "findings_trend", "rai_posture", "environment_posture", "gate_fulfillment", "elevation_audit", "findings_remediation"]},
                "format": {"type": "string", "enum": ["json", "markdown"]},
                "detail_level": {"type": "string", "enum": ["compliance", "full_chain"], "description": "compliance = summary counts; full_chain = complete audit trail per finding/gate"},
            },
            "required": ["project_id", "report_type"],
        },
    },
    {
        "name": "pearl_export_report_pdf",
        "description": (
            "Generate and upload a PDF version of a report to MinIO. "
            "Returns a presigned download URL. "
            "Use pearl_generate_report first to create the report, then call this to get a PDF."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "report_id": {"type": "string", "description": "Report ID from pearl_generate_report"},
            },
            "required": ["project_id", "report_id"],
        },
    },

    # ─── Jobs ────────────────────────────────────────
    {
        "name": "pearl_get_job_status",
        "description": (
            "Get the status of an async job. "
            "Poll this after any tool that returns a job_id (pearl_compile_context, pearl_run_scan, pearl_run_sonar_scan, etc.). "
            "Status values: pending, running, completed, failed. "
            "Poll every few seconds until status is completed or failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },

    # ─── Promotion Gates ─────────────────────────────
    {
        "name": "pearl_evaluate_promotion",
        "description": "Evaluate if a project is ready for promotion to the next environment. Checks all gate rules (security, AI security scan, fairness) and returns pass/fail for each rule with blockers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_environment": {"type": "string", "enum": ["dev", "pilot", "preprod", "prod"], "description": "Optional: target environment. If omitted, evaluates for the next environment in the chain."},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_get_promotion_readiness",
        "description": "Get the latest promotion evaluation for a project. Shows current gate progress, passing/blocking rules, and what needs to be fixed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_environment": {"type": "string", "description": "Filter readiness for a specific target environment (optional)."},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_request_promotion",
        "description": (
            "Request promotion of a project to the next environment. "
            "Evaluates all gates and creates an approval request if evaluation passes. "
            "If gates are still blocking, fix the blockers first using pearl_evaluate_promotion to identify them. "
            "Promotion approval requires human sign-off — stop and await the decision after calling this."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_environment": {"type": "string", "description": "Target environment to promote to (optional — defaults to next in pipeline chain)."},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_get_promotion_history",
        "description": "Get the promotion history for a project — all past environment transitions with who promoted and when.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },

    # ─── Project Summary ─────────────────────────────
    {
        "name": "pearl_get_project_summary",
        "description": "Get a comprehensive project governance summary including policy posture, findings counts, promotion readiness, and fairness status. Returns markdown for readability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "format": {"type": "string", "enum": ["json", "markdown"], "default": "markdown"},
            },
            "required": ["project_id"],
        },
    },

    # ─── Fairness Governance ─────────────────────────
    {
        "name": "pearl_create_fairness_case",
        "description": "Define a fairness case for an AI-enabled project. Includes risk tier, fairness criticality, stakeholders, principles, and recourse model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "risk_tier": {"type": "string", "enum": ["r0", "r1", "r2", "r3", "r4"]},
                "fairness_criticality": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "case_data": {
                    "type": "object",
                    "description": "Fairness case details: system_description, stakeholders, fairness_principles, recourse_model",
                },
            },
            "required": ["project_id", "risk_tier", "fairness_criticality"],
        },
    },
    {
        "name": "pearl_submit_evidence",
        "description": (
            "Submit an evidence package for a project gate control. "
            "Use this after inspecting the project to validate a framework control requirement. "
            "For framework_control_required rules (AIUC-1, OWASP LLM, etc.), inspect the project "
            "codebase for evidence of the control (e.g. rate limiting code, input filtering, security "
            "config, test results) then submit with evidence_type='attestation' and include "
            "control_id (e.g. 'aiuc1/security/b001_2_security_program_integration'), "
            "findings (what you found), and artifact_refs (file paths or URLs). "
            "This satisfies the gate rule without requiring manual baseline editing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "evidence_type": {
                    "type": "string",
                    "enum": ["attestation", "ci_eval_report", "test_results", "runtime_sample", "bias_benchmark", "red_team_report", "guardrail_test", "fairness_audit", "model_card", "manual_review", "sbom", "provenance", "artifact_signed"],
                    "description": "Use 'attestation' for framework control validation (AIUC-1, OWASP LLM, etc.)"
                },
                "evidence_data": {
                    "type": "object",
                    "description": "Evidence details. For attestation: include control_id, findings (what was found), artifact_refs (file paths), and attested_by.",
                },
            },
            "required": ["project_id", "environment", "evidence_type"],
        },
    },
    {
        "name": "pearl_ingest_monitoring_signal",
        "description": "Ingest a runtime fairness monitoring signal (drift, policy violations, stereotype leakage).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "signal_type": {"type": "string", "maxLength": 512, "description": "Signal type (e.g., fairness_drift, policy_violation, stereotype_leakage)"},
                "value": {"type": "number", "description": "Signal value (numeric)"},
                "threshold": {"type": "number", "description": "Optional threshold for comparison"},
                "metadata": {"type": "object"},
            },
            "required": ["project_id", "signal_type", "value"],
        },
    },
    {
        "name": "pearl_submit_context_receipt",
        "description": "Submit proof that an agent consumed fairness context before operating. Links a commit hash to the context artifacts consumed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "commit_hash": {"type": "string"},
                "agent_id": {"type": "string"},
                "tool_calls": {"type": "array", "maxItems": 100, "items": {"type": "string"}},
                "artifact_hashes": {"type": "object"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_sign_fairness_attestation",
        "description": (
            "Sign a fairness evidence package to satisfy the FAIRNESS_ATTESTATION_SIGNED gate rule. "
            "Call this after pearl_submit_evidence to mark the evidence as officially attested. "
            "signed_by should be the agent ID or reviewer ID performing the attestation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "evidence_id": {"type": "string", "description": "Evidence package ID to sign"},
                "signed_by": {"type": "string", "description": "Agent or reviewer ID performing attestation"},
            },
            "required": ["project_id", "evidence_id", "signed_by"],
        },
    },

    # ─── Scan Targets ────────────────────────────────
    {
        "name": "pearl_register_scan_target",
        "description": "Register a repo as a scan target. Use tool_type 'pearl_ai' for PeaRL's built-in AI security scan (default). Other types activate configured external adapters (MASS, SonarQube, SAST, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "repo_url": {"type": "string", "description": "Repository URL to scan"},
                "tool_type": {"type": "string", "enum": ["pearl_ai", "mass", "sonarqube", "sast", "dast", "sca", "container_scan", "iac_scan", "custom"], "description": "Scan provider. 'pearl_ai' uses PeaRL's built-in analyzers. Others require the adapter to be configured."},
                "branch": {"type": "string", "maxLength": 512, "default": "main", "description": "Branch to scan"},
                "scan_frequency": {"type": "string", "enum": ["on_push", "hourly", "daily", "weekly", "on_demand"], "default": "daily"},
                "environment_scope": {"type": "array", "maxItems": 100, "items": {"type": "string"}, "description": "Environments this target applies to"},
                "labels": {"type": "object", "description": "Key-value labels for filtering"},
            },
            "required": ["project_id", "repo_url", "tool_type"],
        },
    },
    {
        "name": "pearl_list_scan_targets",
        "description": "List scan targets registered for a project. Shows repo URLs, tool types, scan frequencies, and last scan status.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_update_scan_target",
        "description": "Update scan target configuration (branch, frequency, status, environment scope).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "scan_target_id": {"type": "string"},
                "branch": {"type": "string"},
                "scan_frequency": {"type": "string", "enum": ["on_push", "hourly", "daily", "weekly", "on_demand"]},
                "status": {"type": "string", "enum": ["active", "paused", "disabled"]},
                "environment_scope": {"type": "array", "maxItems": 100, "items": {"type": "string"}},
                "labels": {"type": "object"},
            },
            "required": ["project_id", "scan_target_id"],
        },
    },

    # ─── AI Security Scanning ────────────────────────
    {
        "name": "pearl_run_scan",
        "description": "Run AI security scan on a target path. Runs context, MCP, workflow, attack surface, RAG, and model file analyzers. Findings are ingested with compliance refs (OWASP LLM, MITRE ATLAS, NIST AI RMF, EU AI Act).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_path": {"type": "string", "description": "Path to directory or file to scan"},
                "analyzers": {"type": "array", "maxItems": 100, "items": {"type": "string", "enum": ["context", "mcp", "workflow", "attack_surface", "rag", "model_file"]}, "description": "Optional: specific analyzers to run (default: all)"},
                "environment": {"type": "string", "enum": ["pilot", "dev", "prod"], "default": "dev"},
            },
            "required": ["project_id", "target_path"],
        },
    },
    {
        "name": "pearl_get_scan_results",
        "description": "Get the latest scan results for a project. Shows findings by severity, compliance scores, and guardrail recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "environment": {"type": "string", "description": "Filter findings by environment (optional — e.g. 'pilot', 'dev', 'prod')."},
                "status": {"type": "string", "enum": ["open", "resolved", "all"], "description": "Filter by finding status (default: open)."},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_assess_compliance",
        "description": "Run compliance scoring against a project's findings. Scores against OWASP LLM Top 10, MITRE ATLAS, NIST AI RMF, and EU AI Act.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_list_guardrails",
        "description": "List available AI security guardrails with implementation guidance. Filter by category (input_validation, output_filtering, rate_limiting, etc.) or severity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "maxLength": 512, "description": "Filter by guardrail category"},
                "severity": {"type": "string", "maxLength": 512, "description": "Filter by severity"},
            },
        },
    },
    {
        "name": "pearl_get_guardrail",
        "description": "Get guardrail detail with implementation steps and code examples.",
        "inputSchema": {
            "type": "object",
            "properties": {"guardrail_id": {"type": "string"}},
            "required": ["guardrail_id"],
        },
    },
    {
        "name": "pearl_get_recommended_guardrails",
        "description": "Get guardrails recommended for a project based on its open findings.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_get_recommended_baseline",
        "description": "Get the recommended governance baseline tier and all 3 tiered baselines (Essential, AI-Standard, AI-Comprehensive). Selection is based on ai_enabled and business_criticality.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ai_enabled": {"type": "boolean", "default": True, "description": "Whether the project uses AI"},
                "business_criticality": {"type": "string", "enum": ["low", "moderate", "high", "mission_critical"], "default": "moderate"},
            },
        },
    },
    {
        "name": "pearl_apply_recommended_baseline",
        "description": "Apply the appropriate tiered governance baseline to a project. Selects tier automatically based on project's ai_enabled and business_criticality.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_list_policy_templates",
        "description": "List AI security policy templates with rules for prompt security, data protection, access control, model security, and more.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "maxLength": 512, "description": "Filter by policy category"},
            },
        },
    },
    {
        "name": "pearl_get_policy_template",
        "description": "Get policy template detail with all rules and implementation guidance.",
        "inputSchema": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    {
        "name": "pearl_ingest_security_review",
        "description": "Parse /security-review markdown output and ingest as PeaRL findings. Extracts finding titles, severity, affected files, and categories from the review prose.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "markdown": {"type": "string", "maxLength": 50000, "description": "Raw markdown output from /security-review"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"], "default": "dev"},
            },
            "required": ["project_id", "markdown"],
        },
    },

    # ─── SonarQube Integration ───────────────────────
    {
        "name": "pearl_trigger_sonar_pull",
        "description": (
            "Pull the latest findings from SonarQube into PeaRL for this project. "
            "Deduplicates findings and returns quality gate status. "
            "Run after sonar-scanner completes to ingest results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_get_sonar_status",
        "description": "Get the current SonarQube quality gate status and finding counts for this project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "pearl_run_sonar_scan",
        "description": (
            "Trigger a SonarQube scan against a registered scan target path. "
            "Returns a job_id — poll pearl_get_job_status for completion. "
            "On completion, findings are automatically pulled into PeaRL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_path": {"type": "string", "description": "Absolute path to scan (must be a registered scan target)"},
            },
            "required": ["project_id", "target_path"],
        },
    },

    # ─── Remediation Execution Bridge ────────────────
    {
        "name": "pearl_claim_task_packet",
        "description": "Claim a task packet for execution as an agent. Sets the packet status to in_progress and records the agent ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packet_id": {"type": "string", "description": "Task packet ID to claim"},
                "agent_id": {"type": "string", "description": "Unique identifier for this agent instance"},
            },
            "required": ["packet_id", "agent_id"],
        },
    },
    {
        "name": "pearl_complete_task_packet",
        "description": "Report the outcome of a task packet execution. Updates finding statuses for resolved findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packet_id": {"type": "string", "description": "Task packet ID to complete"},
                "status": {"type": "string", "enum": ["success", "failed", "partial"], "description": "Outcome status"},
                "changes_summary": {"type": "string", "maxLength": 512, "description": "Human-readable summary of changes made"},
                "finding_ids_resolved": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {"type": "string"},
                    "description": "List of finding IDs that were resolved",
                },
            },
            "required": ["packet_id", "status"],
        },
    },

    # ─── Agent Stage Registration ─────────────────────
    {
        "name": "pearl_register_agent_for_stage",
        "description": (
            "Register an agent or agent team for a specific environment stage on a project. "
            "Sets the agent's role (coordinator, worker, or evaluator) in the project's agent_members, "
            "and optionally configures the environment profile autonomy mode. "
            "Call this when a coordinator begins operating in a new environment — "
            "it binds the team identity to the project before any gate evaluation or task execution."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "PeaRL project ID"},
                "environment": {"type": "string", "description": "Environment stage the agent is operating in (e.g. 'pilot', 'dev', 'prod')"},
                "agent_id": {"type": "string", "description": "Unique identifier for this agent instance (e.g. 'saga-coordinator-v2')"},
                "role": {"type": "string", "enum": ["coordinator", "worker", "evaluator"], "description": "Role of this agent in the team"},
                "autonomy_mode": {"type": "string", "enum": ["assistive", "supervised", "autonomous"], "description": "Autonomy mode to set on the environment profile (optional — leave unset to keep existing)"},
            },
            "required": ["project_id", "environment", "agent_id", "role"],
        },
    },

    # ─── Agent Allowance Profiles ─────────────────────
    {
        "name": "pearl_allowance_check",
        "description": (
            "Check whether an agent action is permitted under its allowance profile. "
            "Evaluates all three enforcement layers: baseline rules, environment tier overrides, "
            "and per-task extensions from the task packet. Returns allowed/denied with reason."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile_id": {"type": "string", "description": "Allowance profile ID (alp_...)"},
                "action": {"type": "string", "maxLength": 512, "description": "The action/command string to evaluate"},
                "agent_id": {"type": "string", "description": "Unique identifier for the agent instance"},
                "task_packet_id": {"type": "string", "description": "Task packet ID for Layer 3 extensions (optional)"},
            },
            "required": ["profile_id", "action", "agent_id"],
        },
    },

    # ─── MASS 2.0 AI Security Scan ───────────────────
    {
        "name": "pearl_trigger_mass_scan",
        "description": (
            "Trigger a MASS 2.0 Claude Agent SDK security scan on an AI application or agent. "
            "Spawns 7 specialized subagents (prompt_injection, rag_vulnerability, mcp_vulnerability, "
            "secret_leak, infra_misconfiguration, model_file_risk, bias_toxicity) to scan the "
            "target codebase, then pushes findings to PeaRL. "
            "Gate rules evaluated: AI_SCAN_COMPLETED, AI_RISK_ACCEPTABLE (threshold 7.0), "
            "NO_PROMPT_INJECTION, CRITICAL_FINDINGS_ZERO. "
            "Blocks gate elevation if risk score >= 7.0. "
            "Re-ingest validates fixes — previously-open findings absent from the new scan are "
            "automatically resolved. "
            "Requires MASS 2.0 SDK installed: cd /path/to/MASS-2.0/sdk && pip install -e ."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "PeaRL project ID to push findings to (e.g. proj_benderbox)"},
                "target_path": {"type": "string", "description": "Absolute path to the AI application/agent codebase to scan"},
                "pearl_api_url": {"type": "string", "description": "PeaRL API base URL (default: http://pearl-api:8080/api/v1)", "default": "http://pearl-api:8080/api/v1"},
                "pearl_api_token": {"type": "string", "description": "PeaRL bearer token (leave empty for local dev)", "default": ""},
                "commit_sha": {"type": "string", "description": "Git commit SHA to anchor this scan (optional)"},
                "branch": {"type": "string", "maxLength": 512, "description": "Git branch name (optional, e.g. dev, main)"},
            },
            "required": ["project_id", "target_path"],
        },
    },

    # ─── Governance Verification ─────────────────────
    {
        "name": "pearl_confirm_claude_md",
        "description": (
            "Confirms the PeaRL governance block is present in the project's CLAUDE.md "
            "and marks the project as governance-verified in PeaRL. "
            "Call this after writing the PeaRL governance block to CLAUDE.md. "
            "Satisfies the CLAUDE_MD_GOVERNANCE_PRESENT gate rule."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "The project ID to mark as governance-verified"},
            },
            "required": ["project_id"],
        },
    },

    # ─── LiteLLM Contract Compliance ──────────────────
    {
        "name": "pearl_submit_contract_snapshot",
        "description": (
            "Submit an agent contract snapshot to PeaRL at provision time. "
            "Call this after provisioning an agent team in LiteLLM to record the approved contract: "
            "which agents were deployed, what LiteLLM agent IDs they received, which virtual key aliases "
            "they use, the skill content hash (for tamper detection), the MCP server allowlist, and "
            "the approved budget. Returns a task_packet_id. Store this ID and pass it to "
            "pearl_check_agent_contract later to detect drift between the snapshot and live state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "PeaRL project ID (proj_...)"},
                "package_id": {"type": "string", "description": "WTK package ID that was provisioned"},
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "dev", "pilot", "preprod", "prod"],
                    "description": "Environment this team is provisioned into",
                },
                "agent_roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 100,
                    "description": "Agent role names in this team (e.g. coordinator, worker, evaluator)",
                },
                "litellm_agent_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 100,
                    "description": "LiteLLM agent IDs assigned during provisioning",
                },
                "key_aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 100,
                    "description": "LiteLLM virtual key aliases this team uses (e.g. vk-worker-agent)",
                },
                "skill_content_hash": {
                    "type": "string",
                    "description": "SHA-256 hash of the compiled skill content (for tamper detection)",
                },
                "mcp_allowlist": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 100,
                    "description": "MCP server names this team is permitted to call",
                },
                "budget_usd": {
                    "type": "number",
                    "description": "Approved per-run budget cap in USD",
                },
            },
            "required": ["project_id", "package_id", "environment"],
        },
    },
    {
        "name": "pearl_check_agent_contract",
        "description": (
            "Check whether a deployed agent's runtime state complies with its approved contract. "
            "Performs two checks: (1) Spend compliance — queries LiteLLM virtual key spend and model usage "
            "against the allowance profile budget and model restrictions. "
            "(2) Drift detection — if a contract snapshot was submitted via pearl_submit_contract_snapshot, "
            "compares the snapshot (agent IDs, skill hash, MCP allowlist, key aliases) against the current "
            "live LiteLLM agent state to detect unauthorized edits since provisioning. "
            "Returns passed=true/false with violations list, plus a drift_check sub-object when a snapshot exists. "
            "Call this before approving promotion to verify the agent stayed within its approved contract."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "packet_id": {"type": "string", "description": "Task packet ID (tp_...) to check contract compliance for."},
            },
            "required": ["packet_id"],
        },
    },
    {
        "name": "pearl_check_litellm_compliance",
        "description": (
            "Check LiteLLM virtual key compliance for a project. "
            "Queries LiteLLM for spend and model violations on one or more virtual key aliases "
            "and returns a list of open compliance findings. "
            "Use this to verify that AI agents operating under a project's virtual keys "
            "have not exceeded budget caps or used unauthorized models. "
            "Returns violations=[] when all keys are within policy."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (proj_...) to check LiteLLM compliance for.",
                },
                "key_aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 100,
                    "description": "Optional list of specific virtual key aliases to check. If omitted, checks all aliases configured on the project's LiteLLM integration endpoint.",
                },
            },
            "required": ["project_id"],
        },
    },

    # ─── Factory Run Summary ──────────────────────────
    {
        "name": "pearl_get_run_summary",
        "description": "Retrieve a factory run summary record by frun_id. Returns aggregated cost, models used, tools called, outcome, and anomaly flags for a completed WTK factory run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "frun_id": {
                    "type": "string",
                    "description": "The factory run ID (= the session_id / frun_id used when pushing cost entries).",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project scope hint (not used for lookup, informational only).",
                },
            },
            "required": ["frun_id"],
        },
    },
]
