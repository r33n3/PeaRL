"""Master API router mounted at /api/v1."""

from fastapi import APIRouter
from pearl.api.routes import (
    agent,
    onboarding,
    approvals,
    audit,
    auth,
    business_units,
    compile,
    compliance,
    context,
    dashboard,
    exceptions,
    fairness,
    findings,
    governance_telemetry,
    guardrails,
    health,
    integrations,
    jobs,
    org_env_config,
    pipelines,
    project_inputs,
    projects,
    promotions,
    remediation,
    reports,
    requirements,
    scan_targets,
    scanning,
    slack_interactions,
    stream,
    task_packets,
    timeline,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(project_inputs.router)
api_router.include_router(jobs.router)
api_router.include_router(compile.router)
api_router.include_router(task_packets.router)
api_router.include_router(findings.router)
api_router.include_router(remediation.router)
api_router.include_router(approvals.router)
api_router.include_router(exceptions.router)
api_router.include_router(reports.router)
api_router.include_router(promotions.router)
api_router.include_router(pipelines.router)
api_router.include_router(fairness.router)
api_router.include_router(context.router)
api_router.include_router(scan_targets.router)
api_router.include_router(scanning.router)
api_router.include_router(guardrails.router)
api_router.include_router(compliance.router)
api_router.include_router(audit.router)
api_router.include_router(governance_telemetry.router)
api_router.include_router(integrations.router)
api_router.include_router(dashboard.router)
api_router.include_router(slack_interactions.router)
api_router.include_router(stream.router)
api_router.include_router(agent.router)
api_router.include_router(business_units.router)
api_router.include_router(org_env_config.router)
api_router.include_router(requirements.router)
api_router.include_router(timeline.router)
api_router.include_router(onboarding.router)
