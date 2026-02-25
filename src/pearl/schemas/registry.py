"""Schema registry mapping logical names to file paths."""

# Maps logical schema names to relative paths under PeaRL_spec/schemas/
SCHEMA_REGISTRY: dict[str, str] = {
    # Common
    "common-defs": "common/common-defs.schema.json",
    "error-response": "common/error-response.schema.json",
    # Project inputs
    "project": "project/project.schema.json",
    "org-baseline": "project/org-baseline.schema.json",
    "application-spec": "project/application-spec.schema.json",
    "environment-profile": "project/environment-profile.schema.json",
    # Compiled outputs
    "compiled-context-package": "context/compiled-context-package.schema.json",
    "task-packet": "context/task-packet.schema.json",
    # Findings + Remediation
    "finding": "findings/finding.schema.json",
    "findings-ingest-request": "findings/findings-ingest-request.schema.json",
    "remediation-spec": "findings/remediation-spec.schema.json",
    # Workflow
    "job-status": "workflow/job-status.schema.json",
    "approval-request": "workflow/approval-request.schema.json",
    "approval-decision": "workflow/approval-decision.schema.json",
    "exception-record": "workflow/exception-record.schema.json",
    "report-request": "workflow/report-request.schema.json",
    "report-response": "workflow/report-response.schema.json",
    # Events
    "webhook-envelope": "events/webhook-envelope.schema.json",
}

# Maps example files to their validating schema (from validate_examples.py)
EXAMPLE_SCHEMA_PAIRS: list[tuple[str, str]] = [
    ("project/create-project.request.json", "project/project.schema.json"),
    ("project/org-baseline.request.json", "project/org-baseline.schema.json"),
    ("project/app-spec.request.json", "project/application-spec.schema.json"),
    ("project/environment-profile.request.json", "project/environment-profile.schema.json"),
    ("compile/compiled-package.response.json", "context/compiled-context-package.schema.json"),
    ("task-packets/generate-task-packet.response.json", "context/task-packet.schema.json"),
    ("findings/findings-ingest.request.json", "findings/findings-ingest-request.schema.json"),
    ("remediation/generate-remediation-spec.response.json", "findings/remediation-spec.schema.json"),
    ("approvals/create-approval.request.json", "workflow/approval-request.schema.json"),
    ("approvals/decision.request.json", "workflow/approval-decision.schema.json"),
    ("exceptions/create-exception.request.json", "workflow/exception-record.schema.json"),
    ("reports/generate-report.request.json", "workflow/report-request.schema.json"),
    ("reports/generate-report.response.json", "workflow/report-response.schema.json"),
]
