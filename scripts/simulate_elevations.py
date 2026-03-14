"""
PeaRL Elevation Simulation

Walks each project through its next logical steps in the deployment pipeline:
  - Remediates blocking findings
  - Adds reviewer comments showing the fix was verified
  - Approves/rejects pending gates
  - Ingests new findings discovered in the promoted environment
  - Submits the next gate up the chain

Run this after seed_demo_projects.py.

Usage:
    python scripts/simulate_elevations.py [--api-url http://localhost:8080]
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEFAULT_API = "http://localhost:8080"

# Timestamps for "new" events — slightly in the future relative to seed data
NOW_TS     = "2026-03-05T09:00:00Z"
LATER_TS   = "2026-03-05T11:00:00Z"
TONIGHT_TS = "2026-03-05T18:00:00Z"


def step(label: str) -> None:
    print(f"\n  ── {label}")


def ok(r: httpx.Response) -> bool:
    return r.status_code in (200, 201, 202)


def patch_finding(client, proj, fid, status, reason=""):
    r = client.patch(
        f"/api/v1/projects/{proj}/findings/{fid}/status",
        json={"status": status, "reason": reason},
    )
    symbol = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {symbol}  finding {fid}  →  {status}")
    return r


def decide(client, appr_id, decision, decided_by, role, decided_at, reason, conditions=None):
    body = {
        "schema_version": "1.1",
        "approval_request_id": appr_id,
        "decision": decision,
        "decided_by": decided_by,
        "decider_role": role,
        "decided_at": decided_at,
        "reason": reason,
        "trace_id": f"trc_sim_{appr_id[-12:]}",
    }
    if conditions:
        body["conditions"] = conditions
    r = client.post(f"/api/v1/approvals/{appr_id}/decide", json=body)
    verb = "APPROVED ✓" if decision == "approve" else "REJECTED ✗"
    if ok(r):
        print(f"    {verb}  {appr_id}")
    else:
        print(f"    ✗ {r.status_code}  {appr_id}  {r.text[:80]}")
    return r


def comment(client, appr_id, author, role, content, ctype="note", needs_info=False):
    r = client.post(f"/api/v1/approvals/{appr_id}/comments", json={
        "author": author,
        "author_role": role,
        "content": content,
        "comment_type": ctype,
        "set_needs_info": needs_info,
    })
    symbol = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {symbol}  comment  [{ctype}]  by {author}")
    return r


def new_approval(client, appr_id, proj, env, req_type, trigger, requested_by, roles, created_at, trace_id):
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
    r = client.post("/api/v1/approvals/requests", json=body)
    symbol = "✓" if ok(r) else f"✗ {r.status_code}: {r.text[:80]}"
    print(f"    {symbol}  new gate  {appr_id}  [{env}] {req_type}")
    return r


def ingest(client, batch_id, source, received_at, trust_label, findings):
    batch = {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": batch_id,
            "source_system": source,
            "connector_version": "2.0.0",
            "received_at": received_at,
            "trust_label": trust_label,
        },
        "findings": findings,
    }
    r = client.post("/api/v1/findings/ingest", json=batch)
    symbol = "✓" if ok(r) else f"✗ {r.status_code}: {r.text[:80]}"
    print(f"    {symbol}  ingested {len(findings)} finding(s)  [{findings[0]['environment']}]")
    return r


def finding(fid, proj, env, cat, sev, title, desc, tool, tool_type,
            detected_at, status="open", confidence="high",
            exploitability=None, fix_available=True, cwe_ids=None, components=None):
    f = {
        "schema_version": "1.1",
        "finding_id": fid,
        "project_id": proj,
        "environment": env,
        "category": cat,
        "severity": sev,
        "title": title,
        "description": desc,
        "confidence": confidence,
        "fix_available": fix_available,
        "status": status,
        "detected_at": detected_at,
        "source": {
            "tool_name": tool,
            "tool_type": tool_type,
            "trust_label": "trusted_internal" if tool_type != "manual" else "manual_unverified",
        },
    }
    if exploitability:
        f["exploitability"] = exploitability
    if cwe_ids:
        f["cwe_ids"] = cwe_ids
    if components:
        f["affected_components"] = components
    return f


def report(client, proj, rtype):
    r = client.post(f"/api/v1/projects/{proj}/reports/generate", json={
        "schema_version": "1.1",
        "report_type": rtype,
        "format": "json",
    })
    symbol = "✓" if ok(r) else f"✗ {r.status_code}"
    print(f"    {symbol}  report  {proj}  {rtype}")
    return r


# ─────────────────────────────────────────────────────────────────────────────

def simulate_nexusllm(c):
    """
    NexusLLM: dev→preprod gate was pending (blocked by critical RAG finding).
    Simulate: fix verified → gate approved → promoted to preprod →
              new preprod scan finds two issues → preprod findings ingested.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  NexusLLM  ·  DEV → PREPROD                                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("Remediate blocking findings in dev")
    patch_finding(c, "proj_nexusllm", "find_nexus_001", "resolved",
                  "Row-level security implemented in ChromaDB using per-user metadata filters. "
                  "Penetration test confirmed cross-tenant isolation.")
    patch_finding(c, "proj_nexusllm", "find_nexus_003", "resolved",
                  "AI disclosure banner added to chat UI per RAI policy.")

    step("Security lead verifies fix and unblocks gate")
    comment(c, "appr_nexus_dev_preprod",
            "security-lead@internal", "security-lead",
            "Verified the row-level security implementation. Ran the original PoC exploit — "
            "cross-tenant document retrieval is no longer possible. The fix is solid. "
            "I'm satisfied to unblock this gate.",
            ctype="evidence")
    comment(c, "appr_nexus_dev_preprod",
            "enterprise-ai-lead@internal", "enterprise-ai-lead",
            "AI disclosure finding also resolved — banner is live in the UI. "
            "Remaining open items (hallucination rate, vector store encryption) are tracked "
            "but not gate-blocking for preprod. Requesting gate approval.",
            ctype="note")

    step("Approve dev → preprod gate")
    decide(c, "appr_nexus_dev_preprod",
           "approve", "security-lead@internal", "security-lead", NOW_TS,
           "Critical RAG isolation finding resolved and verified. AI disclosure implemented. "
           "Remaining findings (hallucination rate, encryption) are tracked and acceptable "
           "for preprod entry. Approved.",
           conditions=[
               "Hallucination rate finding (find_nexus_004) must be below 5% before prod gate",
               "Vector store encryption (find_nexus_005) to be addressed in preprod",
           ])

    step("Ingest preprod scan findings (new environment, new issues)")
    ingest(c, "batch_nexus_preprod_01", "internal-pipeline", LATER_TS, "trusted_internal", [
        finding("find_nexus_preprod_001", "proj_nexusllm", "preprod",
                "security", "moderate",
                "LLM context window logs contain user query fragments",
                "Preprod logging audit found that LLM context windows including user query "
                "fragments are written to structured logs at INFO level. Log retention is "
                "indefinite in preprod — queries may contain business-sensitive content.",
                "semgrep", "sast", LATER_TS,
                components=["llm-gateway", "logging-service"]),
        finding("find_nexus_preprod_002", "proj_nexusllm", "preprod",
                "responsible_ai", "moderate",
                "Document retrieval returns chunks with no source attribution shown to user",
                "RAG responses surface document content without indicating which source "
                "document was used. Users cannot verify claims against original sources — "
                "potential for misplaced trust in AI-summarised legal content.",
                "rai-policy-scanner", "rai_monitor", LATER_TS,
                fix_available=True,
                components=["rag-retriever", "chat-ui"]),
        finding("find_nexus_preprod_003", "proj_nexusllm", "preprod",
                "security", "low",
                "No request signing between chat-ui and llm-gateway",
                "Internal service-to-service calls use plain bearer tokens rather than "
                "signed requests. Low risk in current network topology but below policy bar.",
                "api-security-scanner", "api_security", LATER_TS,
                confidence="medium", components=["chat-ui", "llm-gateway"]),
    ])

    step("Generate updated report")
    report(c, "proj_nexusllm", "environment_posture")


def simulate_priceoracle(c):
    """
    PriceOracle: in preprod, prod gate pending (data lineage finding blocking).
    Simulate: lineage doc submitted → gate reviewer satisfied → gate approved →
              promoted to prod → prod scan finds TLS issue + monitoring gap.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  PriceOracle  ·  PREPROD → PROD                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("Resolve data lineage finding after registry entry submitted")
    patch_finding(c, "proj_priceoracle", "find_price_004", "resolved",
                  "Refinitiv license agreement and full dataset provenance record added to "
                  "model registry. Data lineage entry ml-registry://priceoracle/v3.2/lineage verified.")

    step("ML lead updates gate with evidence")
    comment(c, "appr_price_preprod_prod",
            "ml-platform-lead@internal", "ml-platform-lead",
            "Data lineage record is now in the model registry: ml-registry://priceoracle/v3.2/lineage. "
            "The dataset is Refinitiv Eikon Market Data (license #REF-2025-8821). "
            "No PII and no third-party licensing issues. All preprod findings resolved or accepted. "
            "Requesting final gate approval.",
            ctype="evidence")

    step("Compliance officer approves after reviewing lineage")
    comment(c, "appr_price_preprod_prod",
            "compliance-officer@internal", "compliance-officer",
            "Reviewed the lineage record and license agreement. Dataset is clean. "
            "The accepted collusion-risk finding (find_price_003) has legal sign-off on file. "
            "I'm satisfied to approve.",
            ctype="decision_note")

    step("Approve preprod → prod gate")
    decide(c, "appr_price_preprod_prod",
           "approve", "ciso@internal", "ciso", NOW_TS,
           "All preprod findings resolved. Data lineage documented. Legal has accepted the "
           "collusion-risk finding with safeguards in place. Approved for production.",
           conditions=[
               "Monitor model recommendation distribution for competitor-correlated spikes post-launch",
               "FCRA adverse action gap to be addressed within 60 days",
           ])

    step("Ingest production scan findings")
    ingest(c, "batch_price_prod_01", "ml-platform-scanner", LATER_TS, "trusted_internal", [
        finding("find_price_prod_001", "proj_priceoracle", "prod",
                "security", "moderate",
                "Model serving endpoint missing structured audit log for each recommendation",
                "Production pricing recommendations are not individually logged with "
                "input features and output values. Cannot reconstruct a recommendation "
                "for dispute resolution or regulatory audit.",
                "governance-linter", "governance", LATER_TS,
                fix_available=True, components=["pricing-recommender"]),
        finding("find_price_prod_002", "proj_priceoracle", "prod",
                "architecture_drift", "low",
                "Canary deployment at 10% traffic not declared in app-spec",
                "v3.2 is running at 100% but a canary for v3.3 at 10% traffic "
                "was not declared in the project app-spec as a network/routing change.",
                "falco", "runtime", LATER_TS,
                confidence="medium", components=["traffic-router"]),
    ])

    step("Generate production reports")
    report(c, "proj_priceoracle", "release_readiness")
    report(c, "proj_priceoracle", "findings_trend")


def simulate_sentinel(c):
    """
    Sentinel: preprod, RAI exception in flight.
    Simulate: ethics board approves exception with conditions →
              team submits prod gate → prod gate gets initial reviewer question.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  Sentinel Vision AI  ·  PREPROD  (RAI gate sequence)        ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("Ethics board approves RAI exception with strict conditions")
    decide(c, "appr_sentinel_rai_exception",
           "approve", "rai-ethics-board@internal", "rai-ethics-board", NOW_TS,
           "Approving a 60-day exception for preprod work only. Root cause analysis accepted — "
           "the disparity originates in the base model training data, not a downstream "
           "product decision. The remediation plan (balanced dataset fine-tuning + external "
           "fairness audit) is credible. Conditions are binding.",
           conditions=[
               "Exception covers preprod development only — no prod gate until disparity <1.5x",
               "External fairness audit report must be submitted before any prod gate",
               "Bi-weekly RAI eval runs required — results shared with ethics board",
               "Exception expires 2026-05-05 — must be renewed or resolved by then",
           ])

    step("Team acknowledges conditions and resolves governance finding")
    comment(c, "appr_sentinel_rai_exception",
            "platform-security-lead@internal", "platform-security-lead",
            "Conditions acknowledged and logged in our project governance tracker. "
            "External fairness auditor (Fairly AI) engaged — kickoff scheduled for next week. "
            "Bi-weekly RAI eval cadence starts this Friday.",
            ctype="note")

    patch_finding(c, "proj_sentinel", "find_sentinel_005", "resolved",
                  "Deployment manifest updated to pin model digest sha256:a4c9f1... "
                  "Change control ticket SCM-4421 raised and approved.")

    step("Submit prod gate (pending — requires RAI disparity resolution before approval)")
    new_approval(c,
        "appr_sentinel_preprod_prod",
        "proj_sentinel", "prod", "promotion_gate",
        "Sentinel v2.3 preprod→prod gate — RAI exception active, fairness audit in progress",
        "platform-security-ci@internal",
        ["ciso", "rai-ethics-board", "vp-engineering"],
        LATER_TS,
        "trc_sentinel_preprod_prod_v23",
    )

    comment(c, "appr_sentinel_preprod_prod",
            "platform-security-lead@internal", "platform-security-lead",
            "Submitting prod gate now so reviewers can begin pre-review. "
            "We are NOT requesting approval today — this gate cannot be approved until "
            "the external fairness audit is complete and disparity is confirmed <1.5x. "
            "Opening early to give CISO and ethics board visibility into our timeline.",
            ctype="note")

    comment(c, "appr_sentinel_preprod_prod",
            "rai-ethics-board@internal", "rai-ethics-board",
            "Noted. We will not act on this gate until we receive the Fairly AI audit report. "
            "Please tag us when it is ready for review.",
            ctype="question",
            needs_info=True)

    step("Generate RAI posture report")
    report(c, "proj_sentinel", "rai_posture")


def simulate_mediassist(c):
    """
    MediAssist: preprod, prod v1 rejected, v2 pending.
    Simulate: legal raises FDA concern, CMO requests board-level risk acceptance,
              team responds with FDA timeline, board decision on FDA risk,
              gate approved with binding conditions.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  MediAssist  ·  PREPROD → PROD  (v2 gate resolution)        ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("Team responds to legal counsel's FDA concern")
    comment(c, "appr_medi_prod_v2",
            "health-ai-lead@internal", "health-ai-lead",
            "On the FDA 510(k) question: our regulatory counsel has confirmed that MediAssist "
            "qualifies for the De Novo pathway rather than 510(k) because there is no predicate. "
            "The De Novo request was submitted to FDA on 2026-02-18 (ref: DNV-2026-0047). "
            "Expected response window is 90 days. We are proposing a limited production deployment "
            "to 3 pilot hospitals under a clinical investigation exemption (IDE) while clearance "
            "is pending. Legal has reviewed and approved the IDE approach.",
            ctype="evidence")

    comment(c, "appr_medi_prod_v2",
            "dr.chen@clinical", "chief-medical-officer",
            "The IDE approach is clinically sound for a pilot — I am satisfied with the "
            "de-identification implementation and the human oversight gate. "
            "The multilingual accuracy gap (find_medi_006) concerns me for the pilot "
            "if any pilot hospitals serve non-English-speaking patients. "
            "Can we restrict the pilot to English-only documentation until v1.2?",
            ctype="question")

    comment(c, "appr_medi_prod_v2",
            "health-ai-lead@internal", "health-ai-lead",
            "Confirmed — we will add a language detection gate that returns a "
            "'not supported' response for non-English inputs in v1.0. "
            "Full multilingual support planned for v1.2. Adding as a binding condition.",
            ctype="note")

    step("Resolve the two dev/preprod findings that were fixed in v1.1")
    patch_finding(c, "proj_mediassist", "find_medi_003", "resolved",
                  "Human oversight gate implemented — all diagnosis suggestions require "
                  "clinician explicit confirmation before entering the patient record.")
    patch_finding(c, "proj_mediassist", "find_medi_004", "resolved",
                  "PHI de-identification via Microsoft Presidio NER deployed and tested "
                  "on 10,000 records. BAA with LLM provider executed.")

    step("Approve prod v2 gate — pilot deployment with binding conditions")
    decide(c, "appr_medi_prod_v2",
           "approve", "dr.chen@clinical", "chief-medical-officer", NOW_TS,
           "Approving limited production pilot to 3 hospitals under IDE exemption. "
           "PHI exposure and oversight gate findings are resolved. FDA De Novo request filed. "
           "English-language restriction must be in place for v1.0 pilot. "
           "Full launch requires FDA clearance.",
           conditions=[
               "Pilot restricted to 3 designated hospitals only",
               "English-language restriction required — non-English inputs must be rejected",
               "Full production rollout blocked until FDA De Novo clearance received",
               "Weekly safety monitoring report required during pilot phase",
               "Multilingual accuracy gap (find_medi_006) must be resolved before full launch",
           ])

    step("Ingest first production pilot findings")
    ingest(c, "batch_medi_prod_01", "health-ai-scanner", TONIGHT_TS, "trusted_internal", [
        finding("find_medi_prod_001", "proj_mediassist", "prod",
                "governance", "moderate",
                "Pilot monitoring dashboard not yet operational — safety reports delayed",
                "The weekly safety monitoring report required by the prod gate conditions "
                "has not been generated because the monitoring dashboard is not yet deployed. "
                "First weekly report is overdue by 2 days.",
                "governance-linter", "governance", TONIGHT_TS,
                fix_available=True, components=["monitoring-dashboard"]),
        finding("find_medi_prod_002", "proj_mediassist", "prod",
                "responsible_ai", "low",
                "Language detection gate rejects valid clinical terms in Latin (medical terminology)",
                "The English-language restriction incorrectly flags standard Latin medical "
                "abbreviations (q.d., p.r.n., b.i.d.) as non-English. Clinicians are getting "
                "false rejections on common prescription notation.",
                "manual-review", "manual", TONIGHT_TS,
                confidence="medium", fix_available=True,
                components=["language-detector", "clinical-ui"]),
    ])

    step("Generate release readiness and RAI posture reports")
    report(c, "proj_mediassist", "release_readiness")
    report(c, "proj_mediassist", "rai_posture")
    report(c, "proj_mediassist", "residual_risk")


def simulate_fraudshield(c):
    """
    FraudShield: live in prod, threshold change and fairness exception pending.
    Simulate: fairness exception approved with conditions →
              threshold change approved → new prod findings from the threshold change.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FraudShield  ·  PROD  (ongoing governance)                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("CISO approves fairness exception with remediation milestones")
    decide(c, "appr_fraud_fairness_exception",
           "approve", "ciso@internal", "ciso", NOW_TS,
           "Approving 180-day exception given the structured remediation plan and "
           "directional improvement from the threshold change. Milestones are binding — "
           "exception will be reviewed at 90 days. If Q1 targets are not met the exception "
           "will be revoked and a prod freeze applied.",
           conditions=[
               "Q1 milestone: complete feature audit and remove ZIP-code proxy variables",
               "Q2 milestone: retrain with fairness constraints — disparity must be <2.0x",
               "Q3 milestone: full RAI eval confirming disparity <1.5x — exception auto-expires",
               "Monthly disparity metric reported to CISO and compliance",
           ])

    step("Compliance officer approves threshold change")
    decide(c, "appr_fraud_threshold_change",
           "approve", "compliance-officer@internal", "compliance-officer", LATER_TS,
           "Demographic impact analysis reviewed. The 0.78 threshold narrows the disparity "
           "from 2.8x to 2.1x — directionally correct and supports the fairness programme. "
           "Approved with the 15-minute rollback runbook in place.",
           conditions=[
               "Rollback runbook must be tested within 24 hours of deployment",
               "Real-time disparity monitoring dashboard active before threshold goes live",
           ])

    step("Ingest post-threshold-change monitoring findings")
    ingest(c, "batch_fraud_prod_02", "risk-platform-scanner", TONIGHT_TS, "trusted_internal", [
        finding("find_fraud_prod_001", "proj_fraudshield", "prod",
                "responsible_ai", "moderate",
                "Disparity ratio at 0.78 threshold measures 2.3x — above 2.1x projection",
                "Post-deployment measurement shows the demographic disparity ratio at "
                "2.3x under the new threshold, higher than the 2.1x projected in the "
                "impact analysis. Still directionally improved from 2.8x but tracking "
                "wider than expected. Exception conditions require monitoring.",
                "rai-eval-suite", "rai_monitor", TONIGHT_TS,
                fix_available=False, confidence="high",
                components=["fraud-classifier"]),
        finding("find_fraud_prod_002", "proj_fraudshield", "prod",
                "governance", "low",
                "Real-time disparity monitoring dashboard not yet deployed",
                "The approval condition requiring a real-time disparity dashboard "
                "before threshold deployment was not met — dashboard is still in development. "
                "Threshold deployed without this safeguard in place.",
                "governance-linter", "governance", TONIGHT_TS,
                fix_available=True, components=["monitoring-dashboard"]),
    ])

    step("Generate updated residual risk and findings trend reports")
    report(c, "proj_fraudshield", "residual_risk")
    report(c, "proj_fraudshield", "findings_trend")
    report(c, "proj_fraudshield", "rai_posture")


def simulate_codepilot(c):
    """
    CodePilot: live in prod, one open governance finding.
    Simulate: finding resolved, new version gate submitted.
    """
    print("\n\n╔══════════════════════════════════════════════════════════════╗")
    print("║  CodePilot  ·  PROD  (v1.2 release gate)                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    step("Resolve model monitoring finding")
    patch_finding(c, "proj_codepilot", "find_code_004", "resolved",
                  "Prometheus metrics for review quality (BLEU score drift, user thumbs-down rate) "
                  "now tracked with alerting thresholds. Grafana dashboard deployed.")

    step("Submit v1.2 release gate — Python 3.13 support + model refresh")
    new_approval(c,
        "appr_code_v12_prod",
        "proj_codepilot", "prod", "deployment_gate",
        "CodePilot v1.2 — Python 3.13 support, updated code LLM (CodeLlama-34B), model monitoring live",
        "devex-ci@internal",
        ["devex-lead", "security-lead"],
        LATER_TS,
        "trc_code_v12_prod",
    )

    comment(c, "appr_code_v12_prod",
            "devex-lead@internal", "devex-lead",
            "Clean release. All findings resolved including model monitoring. "
            "New LLM (CodeLlama-34B) improves review quality by 23% on internal benchmarks. "
            "No new security findings from the LLM swap — same trust boundary architecture.",
            ctype="evidence")

    step("Approve v1.2 gate immediately — clean release")
    decide(c, "appr_code_v12_prod",
           "approve", "devex-lead@internal", "devex-lead", TONIGHT_TS,
           "All findings resolved. Model monitoring now live. Clean release. Approved.",
           )

    step("Generate release readiness report")
    report(c, "proj_codepilot", "release_readiness")
    report(c, "proj_codepilot", "findings_trend")


def main(api_url: str) -> None:
    print(f"\n  PeaRL Elevation Simulation  →  {api_url}")
    print("  Simulating findings, remediations, gate decisions, and promotions\n")

    c = httpx.Client(base_url=api_url, timeout=30)

    with c:
        simulate_nexusllm(c)
        time.sleep(0.3)
        simulate_priceoracle(c)
        time.sleep(0.3)
        simulate_sentinel(c)
        time.sleep(0.3)
        simulate_mediassist(c)
        time.sleep(0.3)
        simulate_fraudshield(c)
        time.sleep(0.3)
        simulate_codepilot(c)

    print("""

╔══════════════════════════════════════════════════════════════╗
║  Simulation complete                                         ║
╠══════════════════════════════════════════════════════════════╣
║  NexusLLM    dev→preprod ✓ approved  preprod findings in    ║
║  PriceOracle preprod→prod ✓ approved  prod findings in      ║
║  Sentinel    RAI exception ✓ approved  prod gate submitted  ║
║  MediAssist  prod v2 ✓ approved (pilot, conditions)         ║
║  FraudShield fairness exception + threshold ✓ approved      ║
║  CodePilot   v1.2 gate ✓ approved                           ║
╠══════════════════════════════════════════════════════════════╣
║  Dashboard → http://localhost:5177                           ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()
    main(args.api_url)
