"""MCP tool definitions mapping to PeaRL API operations.

39 tools total (28 existing + 11 scanning/compliance/guardrails tools).
"""

TOOL_DEFINITIONS = [
    # ─── Project Management ──────────────────────────
    {
        "name": "createProject",
        "description": "Create or register a new project for policy enforcement. Requires schema_version, project_id, name, owner_team, business_criticality, external_exposure, and ai_enabled.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "pattern": r"^\d+\.\d+(\.\d+)?$", "default": "1.1"},
                "project_id": {"type": "string", "pattern": "^proj_[A-Za-z0-9_-]+$", "description": "Unique project ID (prefix: proj_)"},
                "name": {"type": "string", "description": "Human-readable project name"},
                "description": {"type": "string"},
                "owner_team": {"type": "string", "description": "Team that owns this project"},
                "business_criticality": {"type": "string", "enum": ["low", "moderate", "high", "mission_critical"]},
                "external_exposure": {"type": "string", "enum": ["internal_only", "partner", "customer_facing", "public"]},
                "ai_enabled": {"type": "boolean", "description": "Whether this project uses AI/LLM capabilities"},
            },
            "required": ["schema_version", "project_id", "name", "owner_team", "business_criticality", "external_exposure", "ai_enabled"],
        },
    },
    {
        "name": "getProject",
        "description": "Get project details by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "updateProject",
        "description": "Update project configuration. Only include fields you want to change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "owner_team": {"type": "string"},
                "business_criticality": {"type": "string", "enum": ["low", "moderate", "high", "mission_critical"]},
                "external_exposure": {"type": "string", "enum": ["internal_only", "partner", "customer_facing", "public"]},
                "ai_enabled": {"type": "boolean"},
            },
            "required": ["project_id"],
        },
    },

    # ─── Project Configuration ───────────────────────
    {
        "name": "upsertOrgBaseline",
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
                        "baseline_id": {"type": "string", "pattern": "^orgb_[A-Za-z0-9_-]+$"},
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
        "name": "upsertApplicationSpec",
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
                        "components": {"type": "array"},
                        "trust_boundaries": {"type": "array"},
                        "data": {"type": "object"},
                    },
                    "required": ["schema_version"],
                },
            },
            "required": ["project_id", "spec"],
        },
    },
    {
        "name": "upsertEnvironmentProfile",
        "description": "Attach or update the environment profile for a project. Defines the environment, delivery stage, risk level, autonomy mode, allowed/blocked capabilities, and approval level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "profile": {
                    "type": "object",
                    "properties": {
                        "schema_version": {"type": "string", "default": "1.1"},
                        "profile_id": {"type": "string", "pattern": "^envp_[A-Za-z0-9_-]+$"},
                        "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                        "delivery_stage": {"type": "string", "enum": ["bootstrap", "prototype", "pilot", "hardening", "preprod", "prod"]},
                        "risk_level": {"type": "string", "enum": ["low", "moderate", "high", "critical"]},
                        "autonomy_mode": {"type": "string", "enum": ["assistive", "supervised_autonomous", "delegated_autonomous", "read_only"]},
                        "allowed_capabilities": {"type": "array", "items": {"type": "string"}},
                        "blocked_capabilities": {"type": "array", "items": {"type": "string"}},
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
        "name": "compileContext",
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
        "name": "getCompiledPackage",
        "description": "Get the latest compiled context package for a project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "generateTaskPacket",
        "description": "Generate a task-scoped context packet from the compiled package. Includes relevant controls, tests, and policy rules for the specific task type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_type": {"type": "string", "enum": ["feature", "fix", "remediation", "refactor", "config", "policy"]},
                "task_summary": {"type": "string"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
            },
            "required": ["project_id", "task_type", "task_summary", "environment"],
        },
    },

    # ─── Findings ────────────────────────────────────
    {
        "name": "ingestFindings",
        "description": "Ingest findings from external security/compliance tools (MASS, SAST, DAST, SCA, etc.). Supports CVSS scores, CWE IDs, compliance references, and MASS verdicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "findings": {"type": "array", "description": "Array of finding objects with finding_id, project_id, source, environment, category, severity, title, and optional cvss_score, cwe_ids, verdict"},
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
        "name": "generateRemediationSpec",
        "description": "Generate a remediation specification from normalized findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "finding_refs": {"type": "array", "items": {"type": "string"}},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
            },
            "required": ["project_id", "finding_refs", "environment"],
        },
    },

    # ─── Approvals & Exceptions ──────────────────────
    {
        "name": "createApprovalRequest",
        "description": "Create an approval request for a policy-relevant action. Returns an approval_request_id to track the request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approval_request_id": {"type": "string", "pattern": "^appr_[A-Za-z0-9_-]+$"},
                "project_id": {"type": "string"},
                "request_type": {"type": "string", "enum": ["deployment_gate", "auth_flow_change", "network_policy_change", "exception", "remediation_execution", "promotion_gate"]},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "request_data": {"type": "object", "description": "Context/details for the approval request"},
            },
            "required": ["approval_request_id", "project_id", "request_type", "environment"],
        },
    },
    {
        "name": "decideApproval",
        "description": "Record an approval decision (approve/reject).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approval_request_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
                "decided_by": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["approval_request_id", "decision", "decided_by"],
        },
    },
    {
        "name": "createException",
        "description": "Create or request a policy exception with rationale and scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "exception_id": {"type": "string", "pattern": "^exc_[A-Za-z0-9_-]+$"},
                "project_id": {"type": "string"},
                "rationale": {"type": "string"},
                "scope": {"type": "object"},
                "expires_at": {"type": "string", "format": "date-time"},
            },
            "required": ["exception_id", "project_id", "rationale"],
        },
    },

    # ─── Reports ─────────────────────────────────────
    {
        "name": "generateReport",
        "description": "Generate a project report (release_readiness, residual_risk, control_coverage, findings_trend, rai_posture, environment_posture).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "report_type": {"type": "string", "enum": ["release_readiness", "residual_risk", "control_coverage", "findings_trend", "rai_posture", "environment_posture"]},
                "format": {"type": "string", "enum": ["json", "markdown"]},
            },
            "required": ["project_id", "report_type"],
        },
    },

    # ─── Jobs ────────────────────────────────────────
    {
        "name": "getJobStatus",
        "description": "Get the status of an async job.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },

    # ─── Promotion Gates (NEW) ───────────────────────
    {
        "name": "evaluatePromotionReadiness",
        "description": "Evaluate if a project is ready for promotion to the next environment. Checks all gate rules (security, MASS AI, fairness) and returns pass/fail for each rule with blockers.",
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
        "name": "getPromotionReadiness",
        "description": "Get the latest promotion evaluation for a project. Shows current gate progress, passing/blocking rules, and what needs to be fixed.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "requestPromotion",
        "description": "Request promotion of a project to the next environment. Evaluates all gates and creates an approval request if evaluation passes.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "getPromotionHistory",
        "description": "Get the promotion history for a project — all past environment transitions with who promoted and when.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },

    # ─── Project Summary (NEW) ───────────────────────
    {
        "name": "getProjectSummary",
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

    # ─── Fairness Governance (NEW) ───────────────────
    {
        "name": "createFairnessCase",
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
        "name": "submitEvidence",
        "description": "Submit a fairness evidence package (CI eval report, bias benchmark, red team report, etc.) for a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "evidence_type": {"type": "string", "enum": ["ci_eval_report", "runtime_sample", "bias_benchmark", "red_team_report", "guardrail_test", "fairness_audit", "model_card", "manual_review"]},
                "evidence_data": {"type": "object", "description": "Evidence details and results"},
            },
            "required": ["project_id", "environment", "evidence_type"],
        },
    },
    {
        "name": "ingestMonitoringSignal",
        "description": "Ingest a runtime fairness monitoring signal (drift, policy violations, stereotype leakage).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"]},
                "signal_type": {"type": "string", "description": "Signal type (e.g., fairness_drift, policy_violation, stereotype_leakage)"},
                "value": {"type": "number", "description": "Signal value (numeric)"},
                "threshold": {"type": "number", "description": "Optional threshold for comparison"},
                "metadata": {"type": "object"},
            },
            "required": ["project_id", "signal_type", "value"],
        },
    },
    {
        "name": "submitContextReceipt",
        "description": "Submit proof that an agent consumed fairness context before operating. Links a commit hash to the context artifacts consumed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "commit_hash": {"type": "string"},
                "agent_id": {"type": "string"},
                "tool_calls": {"type": "array", "items": {"type": "string"}},
                "artifact_hashes": {"type": "object"},
            },
            "required": ["project_id"],
        },
    },

    # ─── Scan Targets (NEW) ──────────────────────────
    {
        "name": "registerScanTarget",
        "description": "Register a repo as a scan target for a scanning tool (MASS, SAST, etc.). Creates a scan target linked to a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "repo_url": {"type": "string", "description": "Repository URL to scan"},
                "tool_type": {"type": "string", "enum": ["mass", "sast", "dast", "sca", "container_scan", "iac_scan", "custom"], "description": "Type of scanning tool"},
                "branch": {"type": "string", "default": "main", "description": "Branch to scan"},
                "scan_frequency": {"type": "string", "enum": ["on_push", "hourly", "daily", "weekly", "on_demand"], "default": "daily"},
                "environment_scope": {"type": "array", "items": {"type": "string"}, "description": "Environments this target applies to"},
                "labels": {"type": "object", "description": "Key-value labels for filtering"},
            },
            "required": ["project_id", "repo_url", "tool_type"],
        },
    },
    {
        "name": "listScanTargets",
        "description": "List scan targets registered for a project. Shows repo URLs, tool types, scan frequencies, and last scan status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "updateScanTarget",
        "description": "Update scan target configuration (branch, frequency, status, environment scope).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "scan_target_id": {"type": "string"},
                "branch": {"type": "string"},
                "scan_frequency": {"type": "string", "enum": ["on_push", "hourly", "daily", "weekly", "on_demand"]},
                "status": {"type": "string", "enum": ["active", "paused", "disabled"]},
                "environment_scope": {"type": "array", "items": {"type": "string"}},
                "labels": {"type": "object"},
            },
            "required": ["project_id", "scan_target_id"],
        },
    },

    # ─── AI Security Scanning ────────────────────────
    {
        "name": "runScan",
        "description": "Run AI security scan on a target path. Runs context, MCP, workflow, attack surface, RAG, and model file analyzers. Findings are ingested with compliance refs (OWASP LLM, MITRE ATLAS, NIST AI RMF, EU AI Act).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_path": {"type": "string", "description": "Path to directory or file to scan"},
                "analyzers": {"type": "array", "items": {"type": "string", "enum": ["context", "mcp", "workflow", "attack_surface", "rag", "model_file"]}, "description": "Optional: specific analyzers to run (default: all)"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"], "default": "dev"},
            },
            "required": ["project_id", "target_path"],
        },
    },
    {
        "name": "getScanResults",
        "description": "Get the latest scan results for a project. Shows findings by severity, compliance scores, and guardrail recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "assessCompliance",
        "description": "Run compliance scoring against a project's findings. Scores against OWASP LLM Top 10, MITRE ATLAS, NIST AI RMF, and EU AI Act.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "listGuardrails",
        "description": "List available AI security guardrails with implementation guidance. Filter by category (input_validation, output_filtering, rate_limiting, etc.) or severity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by guardrail category"},
                "severity": {"type": "string", "description": "Filter by severity"},
            },
        },
    },
    {
        "name": "getGuardrail",
        "description": "Get guardrail detail with implementation steps and code examples.",
        "inputSchema": {
            "type": "object",
            "properties": {"guardrail_id": {"type": "string"}},
            "required": ["guardrail_id"],
        },
    },
    {
        "name": "getRecommendedGuardrails",
        "description": "Get guardrails recommended for a project based on its open findings.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "getRecommendedBaseline",
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
        "name": "applyRecommendedBaseline",
        "description": "Apply the appropriate tiered governance baseline to a project. Selects tier automatically based on project's ai_enabled and business_criticality.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "listPolicyTemplates",
        "description": "List AI security policy templates with rules for prompt security, data protection, access control, model security, and more.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by policy category"},
            },
        },
    },
    {
        "name": "getPolicyTemplate",
        "description": "Get policy template detail with all rules and implementation guidance.",
        "inputSchema": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    {
        "name": "ingestSecurityReview",
        "description": "Parse /security-review markdown output and ingest as PeaRL findings. Extracts finding titles, severity, affected files, and categories from the review prose.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "markdown": {"type": "string", "description": "Raw markdown output from /security-review"},
                "environment": {"type": "string", "enum": ["sandbox", "dev", "pilot", "preprod", "prod"], "default": "dev"},
            },
            "required": ["project_id", "markdown"],
        },
    },
]
