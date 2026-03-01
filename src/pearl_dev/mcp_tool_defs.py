"""MCP tool definitions for pearl-dev developer tools."""

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "pearl_get_task_context",
        "description": (
            "Get a task-scoped policy packet from the compiled context package. "
            "Returns allowed/blocked actions, required tests, approval triggers, "
            "and relevant controls for the current task."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["feature", "fix", "remediation", "refactor", "config", "policy"],
                    "description": "Type of task being performed",
                },
                "task_summary": {
                    "type": "string",
                    "description": "Brief description of the task",
                },
                "affected_components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Component IDs affected by this task",
                },
                "change_hints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hints about what kind of changes will be made",
                },
            },
            "required": ["task_type", "task_summary"],
        },
    },
    {
        "name": "pearl_check_action",
        "description": (
            "Check whether a specific action is allowed by the current policy. "
            "Returns allow, block, or approval_required with the policy reference."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "The action to check (e.g. code_edit, file_write, "
                        "prod_deploy, web_search)"
                    ),
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "pearl_check_diff",
        "description": (
            "Scan a code diff for prohibited patterns such as hardcoded secrets, "
            "wildcard IAM permissions, or undeclared external network calls. "
            "Returns a list of violations found."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff_text": {
                    "type": "string",
                    "description": "The unified diff text to scan",
                },
            },
            "required": ["diff_text"],
        },
    },
    {
        "name": "pearl_request_approval",
        "description": (
            "Request human approval for an action that requires it. "
            "Creates an approval record and returns the approval_id. "
            "IMPORTANT: There is no CLI command to approve this. "
            "Approvals must be reviewed and decided by a human security reviewer "
            "in the PeaRL governance dashboard. "
            "When this tool returns, tell the user: 'This requires human approval. "
            "A security reviewer must approve it in the PeaRL dashboard before you can proceed.' "
            "Do NOT attempt to approve it yourself or suggest any CLI command."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The action requiring approval",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this action is being requested",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context about the request",
                },
            },
            "required": ["action", "reason"],
        },
    },
    {
        "name": "pearl_report_evidence",
        "description": (
            "Log evidence of work completed (test results, code review outcomes, "
            "deployment artifacts). Appends to the audit log."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "evidence_type": {
                    "type": "string",
                    "description": "Type of evidence (e.g. test_results, code_review, artifact)",
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the evidence",
                },
                "details": {
                    "type": "object",
                    "description": "Detailed evidence data",
                },
            },
            "required": ["evidence_type", "summary"],
        },
    },
    {
        "name": "pearl_get_policy_summary",
        "description": (
            "Get a human-readable summary of the current policy. "
            "Includes autonomy mode, allowed/blocked actions, "
            "prohibited patterns, and required tests."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "pearl_check_promotion",
        "description": (
            "Check promotion readiness from locally cached evaluation. "
            "Shows gate progress, passing/blocking rules, and what is required to unblock. "
            "Call evaluatePromotionReadiness first to refresh from the PeaRL API. "
            "IMPORTANT: Blockers that say 'pending human review' or 'EXCEPTION REJECTED' "
            "cannot be resolved by code changes or CLI commands — they require a human "
            "security reviewer to act in the PeaRL governance dashboard. "
            "For rejected exceptions: the fix path is to resolve the issue in code, not request another exception. "
            "For pending exceptions: inform the user and stop — do not suggest any CLI approval commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "pearl_register_repo",
        "description": (
            "Register the current repo as a scan target in PeaRL. "
            "Auto-detects the repo URL from git remote and the project_id "
            "from pearl-dev.toml. Registers with the PeaRL API so scanning "
            "tools (MASS, SAST, etc.) can discover this repo."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "enum": ["mass", "sast", "dast", "sca", "container_scan", "iac_scan", "custom"],
                    "description": "Type of scanning tool (default: mass)",
                    "default": "mass",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to scan (default: current branch)",
                },
                "scan_frequency": {
                    "type": "string",
                    "enum": ["on_push", "hourly", "daily", "weekly", "on_demand"],
                    "description": "How often to scan (default: daily)",
                    "default": "daily",
                },
            },
        },
    },
    {
        "name": "pearl_register_project",
        "description": (
            "Register the current project with PeaRL. Reads project_id and api_url "
            "from .pearl.yaml in the project root. Required fields not in .pearl.yaml "
            "(name, owner_team, business_criticality, external_exposure, ai_enabled) "
            "must be supplied as arguments. Idempotent — safe to call if already registered."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable project name"},
                "owner_team": {"type": "string", "description": "Owning team name"},
                "business_criticality": {
                    "type": "string",
                    "enum": ["low", "moderate", "high", "mission_critical"],
                    "description": "Business criticality level",
                },
                "external_exposure": {
                    "type": "string",
                    "enum": ["internal_only", "partner", "customer_facing", "public"],
                    "description": "Who can access this project's outputs",
                },
                "ai_enabled": {
                    "type": "boolean",
                    "description": "Whether the project uses AI/ML",
                },
                "description": {
                    "type": "string",
                    "description": "Optional project description",
                },
                "bu_id": {
                    "type": "string",
                    "description": "Optional business unit ID (bu_xxx)",
                },
            },
            "required": ["name", "owner_team", "business_criticality", "external_exposure", "ai_enabled"],
        },
    },
    {
        "name": "pearl_get_governance_costs",
        "description": (
            "Get governance cost report for the project. Shows cumulative "
            "cost of running security scans, compliance assessments, and "
            "promotion evaluations through PeaRL Agent SDK. Breaks down "
            "cost by workflow type, model, and over time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "json", "detailed"],
                    "description": "Output format (default: summary)",
                    "default": "summary",
                },
            },
        },
    },
]
