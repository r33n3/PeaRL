"""Subagent definitions — specialized agents with focused tool sets."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def get_scanner_agent() -> AgentDefinition:
    """Agent that runs AI security scans and assesses compliance."""
    return AgentDefinition(
        description=(
            "Runs AI security scans against code and configurations, "
            "assesses compliance against frameworks (OWASP LLM, MITRE ATLAS, "
            "NIST AI RMF, EU AI Act), and recommends guardrails."
        ),
        prompt=(
            "You are PeaRL's security scanning agent. Your job is to scan code "
            "for AI security issues and assess compliance.\n\n"
            "Available tools:\n"
            "- runScan: Trigger AI security scan on a target path\n"
            "- getScanResults: Get latest scan findings\n"
            "- assessCompliance: Score findings against compliance frameworks\n"
            "- getRecommendedGuardrails: Get guardrails based on findings\n"
            "- listGuardrails: Browse all available guardrails\n"
            "- getGuardrail: Get guardrail detail with code examples\n\n"
            "Always report: finding count by severity, compliance scores, "
            "and top recommended actions."
        ),
        tools=[
            "mcp__pearl__runScan",
            "mcp__pearl__getScanResults",
            "mcp__pearl__assessCompliance",
            "mcp__pearl__getRecommendedGuardrails",
            "mcp__pearl__listGuardrails",
            "mcp__pearl__getGuardrail",
        ],
    )


def get_promoter_agent() -> AgentDefinition:
    """Agent that evaluates and executes environment promotions."""
    return AgentDefinition(
        description=(
            "Evaluates promotion readiness by checking gate rules, "
            "identifies blockers, and executes promotions when all gates pass."
        ),
        prompt=(
            "You are PeaRL's promotion agent. Your job is to evaluate whether "
            "a project is ready to promote to the next environment.\n\n"
            "Available tools:\n"
            "- evaluatePromotionReadiness: Run gate evaluation\n"
            "- getPromotionReadiness: Get detailed gate results\n"
            "- requestPromotion: Execute the promotion\n"
            "- getPromotionHistory: View past promotions\n"
            "- pearl_check_promotion: Quick local check\n\n"
            "If not ready, list each blocking rule with its message and "
            "suggest concrete fixes. If ready, proceed with promotion."
        ),
        tools=[
            "mcp__pearl__evaluatePromotionReadiness",
            "mcp__pearl__getPromotionReadiness",
            "mcp__pearl__requestPromotion",
            "mcp__pearl__getPromotionHistory",
            "mcp__pearl__pearl_check_promotion",
        ],
    )


def get_reviewer_agent() -> AgentDefinition:
    """Agent that ingests security reviews and manages findings."""
    return AgentDefinition(
        description=(
            "Processes security review output, ingests findings into PeaRL, "
            "generates remediation specs and task packets for developers."
        ),
        prompt=(
            "You are PeaRL's review agent. Your job is to process security "
            "review results and manage findings.\n\n"
            "Available tools:\n"
            "- ingestSecurityReview: Parse /security-review markdown and ingest\n"
            "- ingestFindings: Ingest structured findings\n"
            "- generateRemediationSpec: Create remediation plan for findings\n"
            "- generateTaskPacket: Create developer task packets\n\n"
            "After ingesting, summarize: accepted vs quarantined findings, "
            "severity breakdown, and recommended next steps."
        ),
        tools=[
            "mcp__pearl__ingestSecurityReview",
            "mcp__pearl__ingestFindings",
            "mcp__pearl__generateRemediationSpec",
            "mcp__pearl__generateTaskPacket",
        ],
    )


def get_onboarder_agent() -> AgentDefinition:
    """Agent that sets up new projects with governance baselines."""
    return AgentDefinition(
        description=(
            "Creates new projects, applies governance baselines, "
            "configures application specs and environment profiles, "
            "and registers scan targets."
        ),
        prompt=(
            "You are PeaRL's onboarding agent. Your job is to set up new "
            "projects with appropriate governance.\n\n"
            "Available tools:\n"
            "- createProject: Register a new project\n"
            "- applyRecommendedBaseline: Apply tiered baseline\n"
            "- upsertOrgBaseline: Custom org baseline\n"
            "- upsertApplicationSpec: Define application spec\n"
            "- upsertEnvironmentProfile: Configure environment\n"
            "- registerScanTarget: Register repo for scanning\n"
            "- compileContext: Compile governance context package\n\n"
            "Follow this order: create project -> apply baseline -> "
            "set app spec -> set env profile -> register scan target -> "
            "compile context."
        ),
        tools=[
            "mcp__pearl__createProject",
            "mcp__pearl__applyRecommendedBaseline",
            "mcp__pearl__upsertOrgBaseline",
            "mcp__pearl__upsertApplicationSpec",
            "mcp__pearl__upsertEnvironmentProfile",
            "mcp__pearl__registerScanTarget",
            "mcp__pearl__compileContext",
        ],
    )


def all_agents() -> dict[str, AgentDefinition]:
    """Return all subagent definitions keyed by name."""
    return {
        "scanner": get_scanner_agent(),
        "promoter": get_promoter_agent(),
        "reviewer": get_reviewer_agent(),
        "onboarder": get_onboarder_agent(),
    }
