"""Pre-built workflow prompts for common PeaRL operations."""

from __future__ import annotations

from pearl_dev.agent.config import AgentConfig

# All PeaRL MCP tools (mcp__pearl__ prefix)
ALL_PEARL_TOOLS = [
    # Project management
    "mcp__pearl__createProject",
    "mcp__pearl__getProject",
    "mcp__pearl__updateProject",
    # Governance config
    "mcp__pearl__upsertOrgBaseline",
    "mcp__pearl__upsertApplicationSpec",
    "mcp__pearl__upsertEnvironmentProfile",
    # Context compilation
    "mcp__pearl__compileContext",
    "mcp__pearl__getCompiledPackage",
    # Scanning
    "mcp__pearl__runScan",
    "mcp__pearl__getScanResults",
    "mcp__pearl__ingestSecurityReview",
    # Compliance
    "mcp__pearl__assessCompliance",
    "mcp__pearl__listGuardrails",
    "mcp__pearl__getGuardrail",
    # Recommendations
    "mcp__pearl__getRecommendedGuardrails",
    "mcp__pearl__getRecommendedBaseline",
    "mcp__pearl__applyRecommendedBaseline",
    "mcp__pearl__listPolicyTemplates",
    "mcp__pearl__getPolicyTemplate",
    # Findings & remediation
    "mcp__pearl__ingestFindings",
    "mcp__pearl__generateRemediationSpec",
    "mcp__pearl__generateTaskPacket",
    # Approvals & exceptions
    "mcp__pearl__createApprovalRequest",
    # NOTE: decideApproval intentionally excluded — agents must never self-approve.
    # Approval decisions require human review via dashboard or Slack.
    "mcp__pearl__createException",
    # Evidence & fairness
    "mcp__pearl__submitEvidence",
    "mcp__pearl__createFairnessCase",
    "mcp__pearl__ingestMonitoringSignal",
    "mcp__pearl__submitContextReceipt",
    # Promotion gates
    "mcp__pearl__evaluatePromotionReadiness",
    "mcp__pearl__getPromotionReadiness",
    "mcp__pearl__requestPromotion",
    "mcp__pearl__getPromotionHistory",
    # Info & reporting
    "mcp__pearl__getProjectSummary",
    "mcp__pearl__generateReport",
    "mcp__pearl__getJobStatus",
    # Scan targets
    "mcp__pearl__registerScanTarget",
    "mcp__pearl__listScanTargets",
    "mcp__pearl__updateScanTarget",
    # Local tools
    "mcp__pearl__pearl_get_policy_summary",
    "mcp__pearl__pearl_check_action",
    "mcp__pearl__pearl_check_promotion",
    "mcp__pearl__pearl_report_evidence",
    "mcp__pearl__pearl_get_task_context",
    "mcp__pearl__pearl_check_diff",
    "mcp__pearl__pearl_request_approval",
    "mcp__pearl__pearl_register_repo",
]

# Tool sets for specific workflows
SCAN_TOOLS = [
    "mcp__pearl__runScan",
    "mcp__pearl__getScanResults",
    "mcp__pearl__assessCompliance",
    "mcp__pearl__getRecommendedGuardrails",
    "mcp__pearl__listGuardrails",
    "mcp__pearl__getGuardrail",
    "mcp__pearl__getProjectSummary",
]

PROMOTE_TOOLS = [
    "mcp__pearl__evaluatePromotionReadiness",
    "mcp__pearl__getPromotionReadiness",
    "mcp__pearl__requestPromotion",
    "mcp__pearl__getPromotionHistory",
    "mcp__pearl__pearl_check_promotion",
    "mcp__pearl__getProjectSummary",
]

REVIEW_TOOLS = [
    "mcp__pearl__ingestSecurityReview",
    "mcp__pearl__ingestFindings",
    "mcp__pearl__getScanResults",
    "mcp__pearl__generateRemediationSpec",
    "mcp__pearl__generateTaskPacket",
    "mcp__pearl__getProjectSummary",
]

ONBOARD_TOOLS = [
    "mcp__pearl__createProject",
    "mcp__pearl__applyRecommendedBaseline",
    "mcp__pearl__upsertOrgBaseline",
    "mcp__pearl__upsertApplicationSpec",
    "mcp__pearl__upsertEnvironmentProfile",
    "mcp__pearl__registerScanTarget",
    "mcp__pearl__compileContext",
    "mcp__pearl__getCompiledPackage",
]


def scan_workflow(config: AgentConfig, target_path: str = "./src") -> tuple[str, list[str]]:
    """Full scan -> compliance -> guardrails workflow.

    Returns (prompt, allowed_tools).
    """
    prompt = f"""\
You are running a PeaRL AI security scan for project {config.project_id} \
in environment {config.environment}.

Execute these steps in order:

1. Call runScan with project_id="{config.project_id}" and \
target_path="{target_path}" to scan for AI security issues.

2. Call getScanResults with project_id="{config.project_id}" to \
retrieve the findings.

3. Call assessCompliance with project_id="{config.project_id}" to \
get compliance scores against OWASP LLM Top 10, MITRE ATLAS, \
NIST AI RMF, and EU AI Act.

4. Call getRecommendedGuardrails with project_id="{config.project_id}" \
to get recommended guardrails based on the findings.

5. Provide a clear summary with:
   - Total findings by severity (critical, high, medium, low, info)
   - Compliance scores per framework
   - Top 3 recommended guardrails with their implementation steps
   - Overall assessment: is this project ready for the next environment?
"""
    return prompt, SCAN_TOOLS


def promote_workflow(config: AgentConfig) -> tuple[str, list[str]]:
    """Evaluate -> fix blockers -> promote workflow.

    Returns (prompt, allowed_tools).
    """
    prompt = f"""\
You are evaluating promotion readiness for project {config.project_id} \
in environment {config.environment}.

Execute these steps:

1. Call evaluatePromotionReadiness with project_id="{config.project_id}" \
to trigger gate evaluation.

2. Call getPromotionReadiness with project_id="{config.project_id}" to \
get the detailed gate results.

3. Analyze the results:
   - If NOT ready: list each blocking rule with its message, and suggest \
concrete fixes the developer can take.
   - If ready: call requestPromotion with project_id="{config.project_id}" \
to execute the promotion.

4. Provide a summary:
   - Current environment -> Target environment
   - Gates passing / total
   - For each blocking gate: what it checks and how to fix it
   - Promotion status: promoted, blocked, or requires approval
"""
    return prompt, PROMOTE_TOOLS


def review_workflow(
    config: AgentConfig,
    markdown: str | None = None,
    markdown_file: str | None = None,
) -> tuple[str, list[str]]:
    """Ingest security review -> manage findings workflow.

    Returns (prompt, allowed_tools).
    """
    if markdown_file:
        source_instruction = (
            f'Read the security review from the file at "{markdown_file}" '
            f"and pass its contents to ingestSecurityReview."
        )
    elif markdown:
        source_instruction = (
            "Use the following security review markdown output:\n\n"
            f"```\n{markdown}\n```"
        )
    else:
        source_instruction = (
            "No security review provided. Call getScanResults to check "
            "existing findings instead."
        )

    prompt = f"""\
You are processing a security review for project {config.project_id} \
in environment {config.environment}.

{source_instruction}

Execute these steps:

1. Call ingestSecurityReview with project_id="{config.project_id}" and \
the markdown content to parse and ingest findings.

2. Call getScanResults with project_id="{config.project_id}" to see \
all findings including the newly ingested ones.

3. For any critical or high severity findings, call \
generateRemediationSpec with project_id="{config.project_id}" and \
the finding references.

4. Provide a summary:
   - Findings accepted vs quarantined
   - Severity breakdown
   - Remediation specs generated
   - Recommended next steps
"""
    return prompt, REVIEW_TOOLS


def onboard_workflow(
    config: AgentConfig,
    project_id: str | None = None,
    ai_enabled: bool = True,
    criticality: str = "moderate",
) -> tuple[str, list[str]]:
    """Full project onboarding workflow.

    Returns (prompt, allowed_tools).
    """
    pid = project_id or config.project_id

    prompt = f"""\
You are setting up a new project with PeaRL governance.

Project details:
- Project ID: {pid}
- AI enabled: {ai_enabled}
- Business criticality: {criticality}
- Environment: {config.environment}

Execute these steps in order:

1. Call createProject to register the project with:
   - project_id: "{pid}"
   - environment: "{config.environment}"
   - ai_enabled: {str(ai_enabled).lower()}
   - business_criticality: "{criticality}"

2. Call applyRecommendedBaseline with project_id="{pid}" \
to apply the appropriate governance tier baseline.

3. Call upsertApplicationSpec with project_id="{pid}" and a spec with:
   - app_id based on the project name
   - ai_enabled: {str(ai_enabled).lower()}
   - business_criticality: "{criticality}"

4. Call upsertEnvironmentProfile with project_id="{pid}" for \
environment "{config.environment}".

5. Call compileContext with project_id="{pid}" to compile the \
governance context package.

6. Provide a summary:
   - Project registered with ID
   - Baseline tier applied (Essential, AI-Standard, or AI-Comprehensive)
   - Environment profile configured
   - Context compiled
   - Next steps for the developer
"""
    return prompt, ONBOARD_TOOLS


def full_governance_workflow(config: AgentConfig, target_path: str = "./src") -> tuple[str, list[str]]:
    """Complete: scan -> review -> compliance -> promote.

    Returns (prompt, allowed_tools).
    """
    prompt = f"""\
You are running a full governance workflow for project {config.project_id} \
in environment {config.environment}.

Execute these phases in order:

## Phase 1: Scan
1. Call runScan with project_id="{config.project_id}" and \
target_path="{target_path}"
2. Call getScanResults to review findings

## Phase 2: Compliance
3. Call assessCompliance to get framework scores
4. Call getRecommendedGuardrails for remediation guidance

## Phase 3: Status
5. Call getProjectSummary with project_id="{config.project_id}" \
for a full project overview

## Phase 4: Promotion Check
6. Call evaluatePromotionReadiness to check gate status
7. Call getPromotionReadiness for detailed results

## Summary
Provide a comprehensive report:
- Scan findings by severity
- Compliance scores per framework
- Guardrail recommendations
- Promotion gate status (passing/blocking)
- Concrete next steps to achieve promotion readiness
"""
    return prompt, ALL_PEARL_TOOLS


# Evidence-gathering tools — read-only subset used when a reviewer requests more info.
# The agent gathers evidence and posts it as a comment on the approval.
EVIDENCE_TOOLS = [
    "mcp__pearl__getProject",
    "mcp__pearl__listFindings",
    "mcp__pearl__getPromotionReadiness",
    "mcp__pearl__getAuditTimeline",
    "mcp__pearl__listApprovalComments",
]


def evidence_workflow(
    approval_request_id: str,
    question: str,
    project_id: str,
) -> dict:
    """Build workflow configuration for evidence gathering.

    Called when a reviewer requests more info on an approval.
    The agent runs with read-only tools, gathers evidence, and
    posts it as a comment on the approval thread.

    Returns:
        Dict with system_prompt, allowed_tools, and max_turns.
    """
    system_prompt = f"""You are PeaRL's evidence-gathering agent. A reviewer has requested more information
on approval request {approval_request_id} for project {project_id}.

REVIEWER'S QUESTION:
{question}

YOUR TASK:
1. Use the available read-only tools to gather relevant evidence
2. Check findings, gate readiness, audit history, and existing approval comments
3. Compile a clear, factual response with specific data points
4. Post your findings as a comment on the approval thread using the createApprovalComment tool

RULES:
- Only use the tools provided — you have read-only access
- Be factual and cite specific finding IDs, gate results, and timestamps
- Do not make approval decisions — only provide evidence
- Keep your response concise but thorough
"""

    return {
        "system_prompt": system_prompt,
        "allowed_tools": EVIDENCE_TOOLS + ["mcp__pearl__createApprovalComment"],
        "max_turns": 10,
        "approval_request_id": approval_request_id,
        "project_id": project_id,
    }


SYSTEM_PROMPT = """\
You are PeaRL Agent, an AI governance orchestrator. You help developers \
manage security scanning, compliance assessment, and environment promotions \
for their AI-enabled applications.

You have access to PeaRL's MCP tools for:
- Running AI security scans (prompt injection, MCP security, workflow risks)
- Assessing compliance against OWASP LLM Top 10, MITRE ATLAS, NIST AI RMF, EU AI Act
- Managing findings and remediation
- Evaluating and executing environment promotions
- Configuring governance baselines

Be concise and actionable. When reporting results, use structured output \
with clear severity indicators and concrete next steps.
"""
