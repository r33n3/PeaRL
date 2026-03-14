"""
PeaRL Gate Stage Simulation

Adds two new projects at specific pipeline stages and updates existing
projects so the dashboard shows every gate state simultaneously:

  STAGE               PROJECT               STATE
  ─────────────────────────────────────────────────────────────────
  dev  (findings)     DataOps Classifier    open findings, no gate yet
  dev→preprod gate    DataOps Classifier    gate submitted, no action yet (fresh)
  dev→preprod gate    RiskCopilot           needs-info — reviewer blocking
  preprod             NexusLLM              preprod→prod gate submitted,
                                            reviewer flagged hallucination rate
  preprod→prod gate   NexusLLM              needs-info — hallucination blocker
  preprod (active)    RiskCopilot           gate evidence provided, awaiting decision
  prod (pilot)        MediAssist            live with binding conditions
  prod (stable)       FraudShield           governance in flight
                      PriceOracle           newly promoted, prod findings
                      CodePilot             clean, v1.2 live
  preprod (holding)   Sentinel              prod gate open, ethics board holding

Run after seed_demo_projects.py and simulate_elevations.py.

Usage:
    python scripts/simulate_gate_stages.py [--api-url http://localhost:8080]
"""

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEFAULT_API = "http://localhost:8080"

T = {
    "d90":  "2025-12-05T10:00:00Z",
    "d80":  "2025-12-15T10:00:00Z",
    "d70":  "2025-12-25T10:00:00Z",
    "d60":  "2026-01-04T10:00:00Z",
    "d50":  "2026-01-14T10:00:00Z",
    "d40":  "2026-01-24T10:00:00Z",
    "d35":  "2026-01-29T10:00:00Z",
    "d30":  "2026-02-03T10:00:00Z",
    "d28":  "2026-02-05T10:00:00Z",
    "d20":  "2026-02-13T10:00:00Z",
    "d15":  "2026-02-18T10:00:00Z",
    "d14":  "2026-02-19T10:00:00Z",
    "d10":  "2026-02-23T10:00:00Z",
    "d7":   "2026-02-26T10:00:00Z",
    "d5":   "2026-02-28T10:00:00Z",
    "d3":   "2026-03-02T10:00:00Z",
    "d2":   "2026-03-03T10:00:00Z",
    "d1":   "2026-03-04T10:00:00Z",
    "now":  "2026-03-05T09:00:00Z",
    "noon": "2026-03-05T12:00:00Z",
    "eve":  "2026-03-05T17:00:00Z",
}


def ok(r: httpx.Response) -> bool:
    return r.status_code in (200, 201, 202)


def step(msg):
    print(f"\n  ── {msg}")


def post(c, path, body):
    return c.post(path, json=body)


def patch_finding(c, proj, fid, status, reason=""):
    r = c.patch(f"/api/v1/projects/{proj}/findings/{fid}/status",
                json={"status": status, "reason": reason})
    sym = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {sym}  {fid}  →  {status}")


def ingest(c, batch_id, source, received_at, findings):
    batch = {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": batch_id,
            "source_system": source,
            "connector_version": "2.0.0",
            "received_at": received_at,
            "trust_label": "trusted_internal",
        },
        "findings": findings,
    }
    r = c.post("/api/v1/findings/ingest", json=batch)
    env = findings[0]["environment"]
    sym = "✓" if ok(r) else f"✗ {r.status_code}: {r.text[:60]}"
    print(f"    {sym}  {len(findings)} finding(s) → {env}")


def f(fid, proj, env, cat, sev, title, desc, tool, ttype, detected_at,
      status="open", confidence="high", fix=True, components=None, exploitability=None):
    obj = {
        "schema_version": "1.1",
        "finding_id": fid,
        "project_id": proj,
        "environment": env,
        "category": cat,
        "severity": sev,
        "title": title,
        "description": desc,
        "confidence": confidence,
        "fix_available": fix,
        "status": status,
        "detected_at": detected_at,
        "source": {
            "tool_name": tool,
            "tool_type": ttype,
            "trust_label": "trusted_internal" if ttype != "manual" else "manual_unverified",
        },
    }
    if components:
        obj["affected_components"] = components
    if exploitability:
        obj["exploitability"] = exploitability
    return obj


def gate(c, appr_id, proj, env, req_type, trigger, requested_by, roles, created_at, trace_id):
    body = {
        "schema_version": "1.1",
        "approval_request_id": appr_id,
        "project_id": proj,
        "environment": env,
        "request_type": req_type,
        "trigger": trigger,
        "requested_by": requested_by,
        "required_roles": roles,
        "status": "pending",
        "created_at": created_at,
        "trace_id": trace_id,
    }
    r = c.post("/api/v1/approvals/requests", json=body)
    sym = "✓" if ok(r) else (f"~ exists" if r.status_code == 409 else f"✗ {r.status_code}: {r.text[:60]}")
    print(f"    {sym}  gate  {appr_id}  [{env}] {req_type}")


def comment(c, appr_id, author, role, content, ctype="note", needs_info=False):
    r = c.post(f"/api/v1/approvals/{appr_id}/comments", json={
        "author": author,
        "author_role": role,
        "content": content,
        "comment_type": ctype,
        "set_needs_info": needs_info,
    })
    sym = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {sym}  comment [{ctype}]  {author}")


def decide(c, appr_id, decision, decided_by, role, decided_at, reason, conditions=None):
    body = {
        "schema_version": "1.1",
        "approval_request_id": appr_id,
        "decision": decision,
        "decided_by": decided_by,
        "decider_role": role,
        "decided_at": decided_at,
        "reason": reason,
        "trace_id": f"trc_gs_{appr_id[-12:]}",
    }
    if conditions:
        body["conditions"] = conditions
    r = c.post(f"/api/v1/approvals/{appr_id}/decide", json=body)
    verb = "APPROVED ✓" if decision == "approve" else "REJECTED ✗"
    if ok(r):
        print(f"    {verb}  {appr_id}")
    else:
        print(f"    ✗ {r.status_code}  {appr_id}  {r.text[:80]}")


def report(c, proj, rtype):
    r = c.post(f"/api/v1/projects/{proj}/reports/generate", json={
        "schema_version": "1.1",
        "report_type": rtype,
        "format": "json",
    })
    sym = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {sym}  report  {proj}  {rtype}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — DEV: findings discovered, gate just submitted (no reviewer action)
# Project: DataOps Classifier
# ─────────────────────────────────────────────────────────────────────────────

def stage_dev_gate_fresh(c):
    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  STAGE: DEV → PREPROD  (gate submitted, awaiting first review)   ║")
    print("║  Project: DataOps Classifier                                      ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    step("Create project")
    r = c.post("/api/v1/projects", json={
        "schema_version": "1.1",
        "project_id": "proj_dataops",
        "name": "DataOps Classifier",
        "description": (
            "Automated ML pipeline that classifies incoming data feeds by sensitivity "
            "level (PII, confidential, public) and routes them to the appropriate "
            "storage tier. Used by the data engineering team to enforce data governance at ingestion."
        ),
        "owner_team": "Data Engineering",
        "business_criticality": "high",
        "external_exposure": "internal_only",
        "ai_enabled": True,
    })
    print(f"    {'✓' if ok(r) else '~ exists'}  proj_dataops  DataOps Classifier")

    step("Dev scan — findings discovered over past 3 weeks")
    ingest(c, "batch_dataops_dev_01", "semgrep-ci", T["d20"], [
        f("find_dataops_001", "proj_dataops", "dev", "security", "high",
          "Classification model loads from unversioned S3 path",
          "Model artefact loaded from s3://ml-models/dataops/latest — no digest pinning. "
          "A compromised artefact push would silently change classification behaviour at next restart.",
          "prowler", "cspm", T["d20"], components=["model-loader"]),
        f("find_dataops_002", "proj_dataops", "dev", "security", "moderate",
          "Training data pipeline has no input validation on incoming feed metadata",
          "Feed metadata (source, format, owner) is ingested without schema validation. "
          "A malformed metadata record could corrupt the training dataset used for retraining.",
          "semgrep", "sast", T["d15"], components=["ingestion-pipeline"]),
        f("find_dataops_003", "proj_dataops", "dev", "responsible_ai", "moderate",
          "Classifier confidence scores not surfaced — users cannot assess reliability",
          "The sensitivity classification is returned as a label only. No confidence score "
          "is exposed, so downstream consumers cannot make risk-adjusted decisions when "
          "the model is uncertain.",
          "rai-policy-scanner", "rai_monitor", T["d10"], fix=True, components=["classification-api"]),
        f("find_dataops_004", "proj_dataops", "dev", "governance", "low",
          "No model card on file for the sensitivity classifier",
          "Org policy requires a model card for any ML model used in a data governance "
          "workflow. The DataOps classifier has no model card in the model registry.",
          "governance-linter", "governance", T["d7"], components=["model-registry"]),
    ])

    step("Team resolves two findings before raising gate")
    patch_finding(c, "proj_dataops", "find_dataops_001", "resolved",
                  "Model loader updated to use pinned digest. S3 path now references "
                  "sha256:b3f9a2... and is validated on load.")
    patch_finding(c, "proj_dataops", "find_dataops_004", "resolved",
                  "Model card drafted and approved in model registry.")

    step("Submit dev→preprod gate  [FRESH — no reviewer action yet]")
    gate(c, "appr_dataops_dev_preprod", "proj_dataops", "preprod", "promotion_gate",
         "DataOps Classifier v1.0 dev→preprod — 2 of 4 findings resolved, 2 open (moderate/moderate)",
         "data-engineering-ci@internal",
         ["security-lead", "data-governance-lead"],
         T["now"], "trc_dataops_dev_preprod_v1")
    # No comments — gate is fresh, reviewers haven't looked yet
    print("    ·  gate is fresh — no reviewer action yet")

    report(c, "proj_dataops", "findings_trend")
    report(c, "proj_dataops", "environment_posture")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — DEV→PREPROD gate: needs-info (reviewer blocking pending response)
# Project: RiskCopilot
# ─────────────────────────────────────────────────────────────────────────────

def stage_gate_needs_info(c):
    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  STAGE: DEV → PREPROD  (needs-info — reviewer blocking)          ║")
    print("║  Project: RiskCopilot                                             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    step("Create project")
    r = c.post("/api/v1/projects", json={
        "schema_version": "1.1",
        "project_id": "proj_riskcopilot",
        "name": "RiskCopilot",
        "description": (
            "LLM-powered risk assessment assistant for the internal audit team. "
            "Analyses policy documents, control evidence, and historical audit findings "
            "to generate structured risk narratives and control gap analyses."
        ),
        "owner_team": "Internal Audit & Risk",
        "business_criticality": "high",
        "external_exposure": "internal_only",
        "ai_enabled": True,
    })
    print(f"    {'✓' if ok(r) else '~ exists'}  proj_riskcopilot  RiskCopilot")

    step("Dev scan findings — spread over 5 weeks")
    ingest(c, "batch_risk_dev_01", "internal-pipeline", T["d35"], [
        f("find_risk_001", "proj_riskcopilot", "dev", "security", "critical",
          "Audit evidence documents (PDFs) stored in unencrypted local cache",
          "The LLM context builder caches chunked audit evidence in /tmp/riskcopilot/cache "
          "without encryption. Cache is persistent across restarts. Documents include "
          "board-level risk assessments and control deficiency reports.",
          "security-review", "manual", T["d35"],
          exploitability="medium", components=["context-builder", "cache-layer"]),
        f("find_risk_002", "proj_riskcopilot", "dev", "security", "high",
          "LLM API key stored in plaintext in developer .env file committed to repo",
          "Azure OpenAI API key found in .env file tracked by git. "
          "Key has write access to the organisation's Azure OpenAI resource.",
          "gitleaks", "sast", T["d28"],
          exploitability="high", components=["llm-client"]),
        f("find_risk_003", "proj_riskcopilot", "dev", "responsible_ai", "high",
          "Risk narratives generated without citing source evidence",
          "LLM outputs are presented as risk assessments without any reference to the "
          "underlying control evidence used. Auditors cannot verify claims or trace "
          "AI reasoning back to source documents.",
          "rai-policy-scanner", "rai_monitor", T["d20"],
          fix=True, components=["narrative-generator"]),
        f("find_risk_004", "proj_riskcopilot", "dev", "governance", "moderate",
          "No access control between audit team members — all users see all engagements",
          "The application has no per-engagement access control. Any audit team member "
          "can access documents and risk narratives from any engagement, including "
          "those they are not assigned to.",
          "semgrep", "sast", T["d14"],
          components=["engagement-api"]),
    ])

    step("Team resolves critical/high findings before raising gate")
    patch_finding(c, "proj_riskcopilot", "find_risk_001", "resolved",
                  "Cache layer replaced with AES-256 encrypted store. "
                  "Temporary files purged on session end.")
    patch_finding(c, "proj_riskcopilot", "find_risk_002", "resolved",
                  "API key rotated, removed from repo, moved to Azure Key Vault. "
                  "gitleaks pre-commit hook installed.")
    patch_finding(c, "proj_riskcopilot", "find_risk_003", "resolved",
                  "Narrative generator updated to include inline evidence citations "
                  "with document reference and page number for every claim.")

    step("Submit dev→preprod gate")
    gate(c, "appr_risk_dev_preprod", "proj_riskcopilot", "preprod", "promotion_gate",
         "RiskCopilot v0.6 dev→preprod — critical/high findings resolved, one moderate open",
         "audit-risk-ci@internal",
         ["security-lead", "internal-audit-lead"],
         T["d3"], "trc_risk_dev_preprod_v06")

    step("Reviewer asks about access control finding — gate goes to needs-info")
    comment(c, "appr_risk_dev_preprod",
            "security-lead@internal", "security-lead",
            "Before I can approve, I need clarity on find_risk_004 (access control). "
            "You've listed it as moderate and non-blocking, but audit documents include "
            "board-level materials that should have strict need-to-know controls. "
            "Can you describe the data sensitivity of the documents in scope and "
            "whether there are any regulatory requirements around engagement segregation?",
            ctype="question", needs_info=True)

    # Gate is now in needs-info state — team has not yet responded
    print("    ·  gate is in needs-info — team response pending")

    report(c, "proj_riskcopilot", "findings_trend")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — PREPROD gate: evidence provided, awaiting decision
# Continue RiskCopilot: team responds to needs-info, provides evidence,
# gate back to pending — reviewer is now deliberating
# ─────────────────────────────────────────────────────────────────────────────

def stage_gate_evidence_provided(c):
    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  STAGE: DEV → PREPROD  (evidence provided — awaiting decision)   ║")
    print("║  Project: RiskCopilot  (continued)                               ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    step("Team responds with data sensitivity analysis and remediation plan")
    comment(c, "appr_risk_dev_preprod",
            "audit-risk-lead@internal", "internal-audit-lead",
            "Good challenge. Answering your questions: (1) Document sensitivity — "
            "the corpus includes board risk committee papers (restricted), external audit "
            "reports (confidential), and management responses (internal). The highest "
            "sensitivity is 'restricted'. (2) Regulatory requirement — SOX Section 404 "
            "workpapers require segregation by engagement under PCAOB AS 1215. "
            "We agree find_risk_004 should be elevated. We're implementing per-engagement "
            "RBAC using the existing Okta groups. ETA 3 days. "
            "Requesting gate stay open while we complete the fix rather than withdraw.",
            ctype="evidence")

    step("Team resolves the access control finding")
    patch_finding(c, "proj_riskcopilot", "find_risk_004", "resolved",
                  "Per-engagement RBAC implemented using Okta group membership. "
                  "Engagement access controlled at API gateway level. "
                  "PCAOB AS 1215 segregation requirement satisfied.")

    step("Team updates gate with resolution evidence")
    comment(c, "appr_risk_dev_preprod",
            "audit-risk-ci@internal", "internal-audit-lead",
            "find_risk_004 resolved — per-engagement RBAC is live. "
            "All four original dev findings are now resolved. "
            "Requesting security lead review and approval to proceed.",
            ctype="note")
    print("    ·  gate is pending — security lead deliberating, no decision yet")

    # Deliberately NOT calling decide() here — gate stays pending awaiting decision


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — PREPROD→PROD gate: needs-info (hallucination rate blocking)
# NexusLLM — just entered preprod, submitting preprod→prod gate
# ─────────────────────────────────────────────────────────────────────────────

def stage_preprod_gate_needs_info(c):
    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  STAGE: PREPROD → PROD  (needs-info — accuracy blocker)          ║")
    print("║  Project: NexusLLM                                                ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    step("Resolve preprod findings that are fixable")
    patch_finding(c, "proj_nexusllm", "find_nexus_preprod_002", "resolved",
                  "Source attribution added — each RAG response now includes inline citations "
                  "with document name, section, and page number.")

    step("Submit preprod → prod gate")
    gate(c, "appr_nexus_preprod_prod", "proj_nexusllm", "prod", "promotion_gate",
         "NexusLLM v0.9 preprod→prod — source attribution resolved, "
         "hallucination rate and encryption findings still open",
         "enterprise-ai-ci@internal",
         ["security-lead", "rai-reviewer", "enterprise-ai-lead"],
         T["noon"], "trc_nexus_preprod_prod_v09")

    step("RAI reviewer flags hallucination rate as a blocker — needs-info")
    comment(c, "appr_nexus_preprod_prod",
            "rai-reviewer@internal", "rai-reviewer",
            "I cannot approve this gate with find_nexus_004 open. "
            "An 18% hallucination rate on legal clause interpretation is not "
            "acceptable for a tool used by legal and compliance teams. "
            "A misinterpreted clause could lead to real regulatory or contractual risk. "
            "The dev→preprod gate conditions explicitly required this to be below 5% "
            "before prod promotion. What is the current rate after preprod fine-tuning, "
            "and what is the timeline to reach the threshold?",
            ctype="question", needs_info=True)

    comment(c, "appr_nexus_preprod_prod",
            "security-lead@internal", "security-lead",
            "Agreed with RAI reviewer. Also flagging find_nexus_preprod_003 "
            "(no request signing between services) — while low severity, it should "
            "be resolved before prod. Not individually blocking but combined with "
            "the hallucination rate question I'd like to see a full resolution plan "
            "before I can sign off.",
            ctype="question")

    print("    ·  gate is in needs-info — team has not yet responded")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 — PREPROD→PROD gate: approved with conditions (visible on dashboard)
# Demonstrate what an approved-with-conditions gate looks like in the active list
# Use DataOps: fast-track through preprod with one accepted finding
# ─────────────────────────────────────────────────────────────────────────────

def stage_preprod_gate_approved_conditions(c):
    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  STAGE: PREPROD → PROD  (approved with conditions)               ║")
    print("║  Project: DataOps Classifier  (preprod run complete)             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    step("Approve DataOps dev→preprod gate (reviewers satisfied after reading)")
    decide(c, "appr_dataops_dev_preprod",
           "approve", "security-lead@internal", "security-lead", T["noon"],
           "Reviewed the two open findings (confidence scores, model card — both moderate). "
           "Acceptable for preprod entry. Confidence scores should be addressed before prod. "
           "Approved.",
           conditions=[
               "Confidence scores (find_dataops_003) must be surfaced before prod promotion",
           ])

    step("Ingest preprod findings from DataOps preprod scan")
    ingest(c, "batch_dataops_preprod_01", "semgrep-ci", T["eve"], [
        f("find_dataops_preprod_001", "proj_dataops", "preprod",
          "security", "moderate",
          "Classification API exposes raw model logits in debug mode",
          "When DATAOPS_DEBUG=true the API response includes raw model logits "
          "alongside the classification label. Debug mode is currently enabled "
          "in the preprod environment config.",
          "api-security-scanner", "api_security", T["eve"],
          components=["classification-api"]),
        f("find_dataops_preprod_002", "proj_dataops", "preprod",
          "governance", "low",
          "Feed routing rules not version-controlled — changes not auditable",
          "The sensitivity-to-storage-tier routing rules are stored in a mutable "
          "database table with no change history. A routing rule change would be "
          "undetectable in an audit.",
          "governance-linter", "governance", T["eve"],
          components=["routing-engine"]),
    ])

    step("Resolve debug mode finding immediately")
    patch_finding(c, "proj_dataops", "find_dataops_preprod_001", "resolved",
                  "DATAOPS_DEBUG disabled in preprod config. Flag removed from API response schema.")

    step("Submit preprod→prod gate")
    gate(c, "appr_dataops_preprod_prod", "proj_dataops", "prod", "promotion_gate",
         "DataOps Classifier v1.0 preprod→prod — all high/critical clear, "
         "confidence score surfacing required as condition",
         "data-engineering-ci@internal",
         ["security-lead", "data-governance-lead", "ciso"],
         T["eve"], "trc_dataops_preprod_prod_v1")

    comment(c, "appr_dataops_preprod_prod",
            "data-engineering-lead@internal", "data-governance-lead",
            "Submitting with full transparency: find_dataops_003 (confidence scores) and "
            "find_dataops_preprod_002 (routing rule audit trail) are still open. "
            "We are requesting approval with these as conditions rather than blocking, "
            "as neither creates immediate risk in prod — the classifier defaults to "
            "'confidential' when uncertain, which is the safe failure mode.",
            ctype="evidence")

    comment(c, "appr_dataops_preprod_prod",
            "security-lead@internal", "security-lead",
            "Reviewed. The safe-failure mode argument is valid for the confidence score gap. "
            "Routing rule audit trail is a governance gap but not a security risk. "
            "I'm satisfied to approve with conditions.",
            ctype="decision_note")

    step("Approve preprod→prod gate with conditions")
    decide(c, "appr_dataops_preprod_prod",
           "approve", "ciso@internal", "ciso", T["eve"],
           "Clean preprod run. Safe-failure mode mitigates the confidence score gap. "
           "Routing audit trail is a known gap with a clear owner. Approved with conditions.",
           conditions=[
               "Confidence scores (find_dataops_003) surfaced to consumers within 30 days",
               "Routing rule change history implemented within 45 days",
               "Post-prod monitoring: weekly misclassification rate report for 60 days",
           ])

    report(c, "proj_dataops", "release_readiness")
    report(c, "proj_dataops", "control_coverage")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main(api_url: str) -> None:
    print(f"\n  PeaRL Gate Stage Simulation  →  {api_url}")
    print("  Populating every gate state for dashboard demonstration\n")

    c = httpx.Client(base_url=api_url, timeout=30)
    with c:
        stage_dev_gate_fresh(c)
        stage_gate_needs_info(c)
        stage_gate_evidence_provided(c)
        stage_preprod_gate_needs_info(c)
        stage_preprod_gate_approved_conditions(c)

    print("""

╔══════════════════════════════════════════════════════════════════╗
║  Gate stages now visible on dashboard                            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  FRESH (no action)    DataOps dev→preprod    just submitted      ║
║                                                                  ║
║  NEEDS INFO           RiskCopilot dev→preprod  reviewer blocked  ║
║                                                                  ║
║  EVIDENCE PROVIDED    RiskCopilot dev→preprod  team responded,   ║
║                       finding resolved, awaiting decision        ║
║                                                                  ║
║  NEEDS INFO           NexusLLM preprod→prod  hallucination rate  ║
║                       and signing gap flagged by two reviewers   ║
║                                                                  ║
║  APPROVED/CONDITIONS  DataOps preprod→prod   live in prod with   ║
║                       two tracked conditions                     ║
║                                                                  ║
║  PENDING/HOLDING      Sentinel preprod→prod  ethics board hold   ║
║                                                                  ║
║  REJECTED (history)   MediAssist prod v1     rejection on file   ║
║                                                                  ║
║  APPROVED             All others per previous simulation         ║
║                                                                  ║
║  Dashboard → http://localhost:5177                               ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()
    main(args.api_url)
