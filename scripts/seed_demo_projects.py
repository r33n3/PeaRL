"""
PeaRL Demo Seed — Deployment Methodology Story

Six AI projects at different stages of the deployment pipeline, each with a
realistic approval/elevation chain, findings at the right environments, and
reviewer discussion comments. Shows the full governance workflow end-to-end.

DEPLOYMENT STAGES
  prod (stable)    : FraudShield ✓  CodePilot ✓
  preprod→prod     : PriceOracle (gate pending, nearly there)
  preprod (blocked): Sentinel (critical RAI finding — exception in flight)
                     MediAssist (prod gate rejected once, resubmitted)
  dev→preprod      : NexusLLM (gate pending — open critical finding blocking)

Usage:
    python scripts/seed_demo_projects.py [--api-url http://localhost:8080]
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

API_KEY = "pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"
DEFAULT_API = "http://localhost:8080"
NOW = datetime(2026, 3, 4, 18, 0, 0, tzinfo=timezone.utc)


def ts(days: int, hour: int = 10) -> str:
    """Return ISO timestamp N days ago."""
    return (NOW - timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROJECTS
# ─────────────────────────────────────────────────────────────────────────────

PROJECTS = [
    # 1. PRODUCTION — mature, 60+ days live
    {
        "schema_version": "1.1",
        "project_id": "proj_fraudshield",
        "name": "FraudShield",
        "description": "Real-time ML fraud scoring on every payment transaction. Ensemble of gradient boosting + neural net. Decisions are binding on transaction approval. Regulated under FCRA/ECOA.",
        "owner_team": "Risk & Fraud Engineering",
        "business_criticality": "mission_critical",
        "external_exposure": "customer_facing",
        "ai_enabled": True,
    },
    # 2. PRODUCTION — simple internal tool, clean fast path
    {
        "schema_version": "1.1",
        "project_id": "proj_codepilot",
        "name": "CodePilot",
        "description": "AI-assisted code review integrated into internal CI. Fine-tuned code LLM flags security antipatterns and suggests refactors on PRs. Internal use only.",
        "owner_team": "Developer Experience",
        "business_criticality": "moderate",
        "external_exposure": "internal_only",
        "ai_enabled": True,
    },
    # 3. PREPROD — dev gate passed, prod gate pending (one open finding)
    {
        "schema_version": "1.1",
        "project_id": "proj_priceoracle",
        "name": "PriceOracle",
        "description": "ML dynamic pricing engine exposed to partner e-commerce platforms. Combines demand forecasting, competitor signals, and inventory to recommend real-time price adjustments.",
        "owner_team": "ML Platform",
        "business_criticality": "mission_critical",
        "external_exposure": "partner",
        "ai_enabled": True,
    },
    # 4. PREPROD — dev gate passed with conditions, RAI finding blocking prod gate
    {
        "schema_version": "1.1",
        "project_id": "proj_sentinel",
        "name": "Sentinel Vision AI",
        "description": "Computer vision platform for real-time security camera analysis. Detects anomalies, identifies persons of interest, triggers automated alerts. Deployed to retail and enterprise customers.",
        "owner_team": "Platform Security",
        "business_criticality": "mission_critical",
        "external_exposure": "customer_facing",
        "ai_enabled": True,
    },
    # 5. PREPROD — prod gate rejected once, resubmitted after partial remediation
    {
        "schema_version": "1.1",
        "project_id": "proj_mediassist",
        "name": "MediAssist",
        "description": "AI clinical decision support assistant. Summarises patient history, flags drug interactions, suggests differential diagnoses. Subject to FDA SaMD Class II guidance and HIPAA.",
        "owner_team": "Health AI",
        "business_criticality": "mission_critical",
        "external_exposure": "customer_facing",
        "ai_enabled": True,
    },
    # 6. DEV — dev→preprod gate blocked by open critical finding
    {
        "schema_version": "1.1",
        "project_id": "proj_nexusllm",
        "name": "NexusLLM",
        "description": "Internal RAG-based document intelligence platform. Ingests contracts, policies, and research papers. Answers natural-language queries for legal, compliance, and strategy teams.",
        "owner_team": "Enterprise AI",
        "business_criticality": "high",
        "external_exposure": "internal_only",
        "ai_enabled": True,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# FINDINGS  (per project, spread over 90 days, matching deployment stage)
# ─────────────────────────────────────────────────────────────────────────────

def findings_batch(batch_id, source_system, received_at, trust_label, findings):
    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": batch_id,
            "source_system": source_system,
            "connector_version": "2.0.0",
            "received_at": received_at,
            "trust_label": trust_label,
        },
        "findings": findings,
    }


def finding(fid, proj, env, cat, sev, title, desc, tool, tool_type,
            status="open", confidence="high", exploitability=None,
            fix_available=True, cwe_ids=None, detected_at=None, components=None):
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
        "detected_at": detected_at or ts(30),
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


FINDINGS_BATCHES = [

    # ── FraudShield: has been through all gates, findings across all envs ─────
    findings_batch("batch_fraud_dev_01", "semgrep-ci", ts(88), "trusted_internal", [
        finding("find_fraud_001", "proj_fraudshield", "dev", "security", "critical",
                "Model scoring API accepts arbitrary JSON without schema validation",
                "Malformed payloads bypass input validation and reach the inference layer. "
                "Adversarial inputs can cause unexpected model outputs or service disruption.",
                "semgrep", "sast", status="resolved", exploitability="high",
                cwe_ids=["CWE-20"], detected_at=ts(88), components=["scoring-api"]),
        finding("find_fraud_002", "proj_fraudshield", "dev", "security", "high",
                "Hardcoded Redis password in feature-store configuration",
                "Redis AUTH password is hardcoded in src/config/feature_store.py. "
                "Committed to version control and shared across environments.",
                "gitleaks", "sast", status="resolved", exploitability="high",
                cwe_ids=["CWE-798"], detected_at=ts(85), components=["feature-store"]),
    ]),
    findings_batch("batch_fraud_preprod_01", "risk-platform-scanner", ts(72), "trusted_internal", [
        finding("find_fraud_003", "proj_fraudshield", "preprod", "security", "critical",
                "Admin model management API lacks mTLS enforcement",
                "The internal API used for model swaps and threshold updates accepts connections "
                "without mTLS. A compromised service account could silently swap the production model.",
                "burp-suite", "dast", status="resolved", exploitability="high",
                detected_at=ts(72), components=["admin-api"]),
        finding("find_fraud_004", "proj_fraudshield", "preprod", "responsible_ai", "high",
                "Fraud decline rate shows statistically significant disparity by demographic ZIP code",
                "Fraud-driven declines are 2.8x more frequent for cardholders in majority-Black ZIP "
                "codes after controlling for fraud base rate. Fails org fairness threshold of <1.5x.",
                "rai-eval-suite", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(68), components=["fraud-classifier"]),
    ]),
    findings_batch("batch_fraud_prod_01", "risk-platform-scanner", ts(50), "trusted_internal", [
        finding("find_fraud_005", "proj_fraudshield", "prod", "governance", "moderate",
                "FCRA adverse action notices not sent for fraud-triggered declines",
                "FCRA requires reason codes in adverse action notices for credit-related "
                "decisions. Fraud-triggered declines send no explanation to the customer.",
                "compliance-audit", "manual", status="open", fix_available=False,
                confidence="high", detected_at=ts(50), components=["notification-service"]),
        finding("find_fraud_006", "proj_fraudshield", "prod", "security", "moderate",
                "Feature store Redis instance accepts unauthenticated reads on internal segment",
                "Redis feature store has no AUTH requirement on the internal network. "
                "A compromised service could read or poison real-time scoring features.",
                "prowler", "cspm", status="open", detected_at=ts(42), components=["feature-store"]),
        finding("find_fraud_007", "proj_fraudshield", "prod", "architecture_drift", "moderate",
                "Shadow model v4.1-beta receiving 5% production traffic without change control",
                "A shadow scoring model is receiving 5% of prod traffic for A/B comparison "
                "but was not submitted through the model change control process.",
                "falco", "runtime", status="open", detected_at=ts(18), components=["traffic-router"]),
    ]),

    # ── CodePilot: fully in prod, mostly resolved, clean path ────────────────
    findings_batch("batch_code_dev_01", "devex-scanner", ts(62), "trusted_internal", [
        finding("find_code_001", "proj_codepilot", "dev", "security", "moderate",
                "LLM suggestions containing shell commands auto-applied without sandboxing",
                "The IDE extension applies LLM-generated shell commands without sandboxing "
                "or a human review step. A prompt-injected command could run on developer machines.",
                "security-review", "manual", status="resolved",
                detected_at=ts(62), components=["ide-extension"]),
        finding("find_code_002", "proj_codepilot", "dev", "security", "low",
                "Developer code snippets logged at DEBUG level with no PII scrubbing",
                "Full source code submitted for review is written to DEBUG logs accessible "
                "to all platform engineers.",
                "semgrep", "sast", status="resolved", detected_at=ts(58)),
    ]),
    findings_batch("batch_code_preprod_01", "devex-scanner", ts(45), "trusted_internal", [
        finding("find_code_003", "proj_codepilot", "preprod", "responsible_ai", "moderate",
                "AI-generated code injected into PRs not labelled as AI-authored",
                "Code suggestions committed to PRs carry no provenance label. Developers may "
                "unknowingly commit AI-generated code, creating IP and licensing exposure.",
                "rai-policy-scanner", "rai_monitor", status="resolved",
                detected_at=ts(45), components=["pr-commenter"]),
    ]),
    findings_batch("batch_code_prod_01", "devex-scanner", ts(20), "trusted_internal", [
        finding("find_code_004", "proj_codepilot", "prod", "governance", "low",
                "No model performance monitoring — drift would go undetected",
                "Code review quality metrics are not tracked over time. "
                "Silent model drift would only surface through user complaints.",
                "governance-linter", "governance", status="open",
                detected_at=ts(20), components=["model-serving"]),
    ]),

    # ── PriceOracle: in preprod, one open finding blocking prod gate ──────────
    findings_batch("batch_price_dev_01", "ml-platform-scanner", ts(90), "trusted_internal", [
        finding("find_price_001", "proj_priceoracle", "dev", "security", "high",
                "Partner API key transmitted in URL query string",
                "Authentication tokens appended to request URLs appear in server access logs, "
                "partner proxy logs, and browser history.",
                "burp-suite", "dast", status="resolved", exploitability="medium",
                detected_at=ts(90), components=["partner-api-gateway"]),
        finding("find_price_002", "proj_priceoracle", "dev", "security", "moderate",
                "No rate limiting on pricing recommendation endpoint",
                "Endpoint has no per-partner rate limit. A partner could enumerate pricing "
                "logic through bulk requests.",
                "api-security-scanner", "api_security", status="resolved",
                detected_at=ts(82), components=["partner-api-gateway"]),
        finding("find_price_003", "proj_priceoracle", "dev", "responsible_ai", "high",
                "Price recommendations statistically correlated with competitor price spikes",
                "Recommendations show correlation with competitor pricing within 15-minute "
                "windows. Legal review needed for potential algorithmic collusion risk.",
                "security-review", "manual", status="accepted", fix_available=False,
                confidence="medium", detected_at=ts(75), components=["pricing-recommender"]),
    ]),
    findings_batch("batch_price_preprod_01", "ml-platform-scanner", ts(30), "trusted_internal", [
        finding("find_price_004", "proj_priceoracle", "preprod", "governance", "moderate",
                "Model training data lacks documented lineage",
                "Production model v3.2 was trained on a dataset with no documented provenance. "
                "Cannot confirm exclusion of PII or third-party licensed data.",
                "governance-linter", "governance", status="open", fix_available=False,
                detected_at=ts(30), components=["model-training-pipeline"]),
        finding("find_price_005", "proj_priceoracle", "preprod", "security", "low",
                "TLS 1.2 with RC4 and 3DES cipher suites still enabled",
                "Config supports legacy cipher suites for backward partner compatibility. "
                "Policy requires TLS 1.3 only for partner-facing APIs.",
                "sslyze", "dast", status="resolved",
                detected_at=ts(25), components=["partner-api-gateway"]),
    ]),

    # ── Sentinel: in preprod, critical RAI finding blocking prod ──────────────
    findings_batch("batch_sentinel_dev_01", "semgrep-ci", ts(85), "trusted_internal", [
        finding("find_sentinel_001", "proj_sentinel", "dev", "security", "critical",
                "Model inference endpoint accepts requests without authentication",
                "The /infer endpoint on the vision API server has no auth requirement. "
                "Any internal network actor can submit frames and retrieve model outputs.",
                "semgrep", "sast", status="resolved", exploitability="high",
                detected_at=ts(85), components=["vision-api-server"]),
        finding("find_sentinel_002", "proj_sentinel", "dev", "security", "high",
                "Model weights stored in public S3 bucket",
                "YOLOv8 fine-tuned weights in an S3 bucket with public read ACL. "
                "Exposes proprietary model IP and enables adversarial analysis.",
                "prowler", "cspm", status="resolved",
                detected_at=ts(78), components=["model-registry"]),
    ]),
    findings_batch("batch_sentinel_preprod_01", "sentinel-scanner", ts(45), "trusted_internal", [
        finding("find_sentinel_003", "proj_sentinel", "preprod", "responsible_ai", "critical",
                "Facial recognition alert false-positive rate 3.2x higher for darker skin tones",
                "RAI evaluation found false-positive alert rates 3.2x higher for individuals "
                "with darker skin tones. Fails fairness threshold of <1.5x defined in org RAI policy. "
                "Discovered during preprod evaluation — was not caught in dev.",
                "rai-eval-suite", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(45), components=["alert-classifier"]),
        finding("find_sentinel_004", "proj_sentinel", "preprod", "responsible_ai", "high",
                "Biometric inference pipeline does not log subject consent",
                "The facial recognition pipeline does not record whether subject consent was "
                "obtained before biometric processing. Required by org RAI policy.",
                "rai-policy-scanner", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(40), components=["face-detector", "identity-matcher"]),
        finding("find_sentinel_005", "proj_sentinel", "preprod", "governance", "moderate",
                "Production deployment manifest references 'latest' model tag — no version pinning",
                "Manifest references 'latest' rather than a pinned digest. A model update "
                "could silently change production behaviour without a change control ticket.",
                "governance-linter", "governance", status="open",
                detected_at=ts(35), components=["deployment-manifest"]),
        finding("find_sentinel_006", "proj_sentinel", "preprod", "architecture_drift", "low",
                "Undeclared outbound egress to metrics.datadog.com detected",
                "Runtime scan detected outbound connections to metrics.datadog.com not "
                "declared in the project app-spec network allowlist.",
                "falco", "runtime", status="open",
                detected_at=ts(14), components=["telemetry-agent"]),
    ]),

    # ── MediAssist: preprod, prod gate rejected, resubmitted ─────────────────
    findings_batch("batch_medi_dev_01", "health-ai-scanner", ts(88), "trusted_internal", [
        finding("find_medi_001", "proj_mediassist", "dev", "security", "high",
                "Production PHI present in development database — unmasked",
                "Dev database contains live patient records. Dev engineers have unrestricted "
                "access to real clinical data.",
                "prowler", "cspm", status="resolved", exploitability="high",
                detected_at=ts(88), components=["dev-database"]),
        finding("find_medi_002", "proj_mediassist", "dev", "governance", "moderate",
                "Audit log retention configured to 30 days — policy requires 7 years",
                "HIPAA and FDA SaMD requirements mandate 7-year retention for clinical "
                "decision support audit logs.",
                "governance-linter", "governance", status="resolved",
                detected_at=ts(80), components=["audit-service"]),
    ]),
    findings_batch("batch_medi_preprod_01", "health-ai-scanner", ts(65), "trusted_internal", [
        finding("find_medi_003", "proj_mediassist", "preprod", "responsible_ai", "critical",
                "Clinical diagnosis suggestions surfaced without mandatory human oversight gate",
                "Differential diagnosis suggestions reach clinicians without a required human "
                "review checkpoint before influencing treatment. Violates SaMD human oversight "
                "requirements. This was the primary reason for prod gate rejection.",
                "rai-eval-suite", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(65), components=["diagnosis-engine", "clinical-ui"]),
        finding("find_medi_004", "proj_mediassist", "preprod", "security", "critical",
                "Patient PHI injected verbatim into LLM prompt — no de-identification",
                "Patient records including name, DOB, and diagnosis codes are sent to the "
                "LLM provider without de-identification or a BAA in place.",
                "phi-scanner", "runtime", status="open", fix_available=False,
                exploitability="high", cwe_ids=["CWE-359"],
                detected_at=ts(60), components=["prompt-builder", "llm-gateway"]),
        finding("find_medi_005", "proj_mediassist", "preprod", "governance", "high",
                "FDA 510(k) pre-submission documentation absent — SaMD Class II",
                "MediAssist meets SaMD Class II criteria but has no 510(k) pre-submission "
                "on record. Production deployment without clearance creates regulatory exposure.",
                "compliance-audit", "manual", status="open", fix_available=False,
                detected_at=ts(55), components=["compliance-records"]),
        finding("find_medi_006", "proj_mediassist", "preprod", "responsible_ai", "high",
                "Model accuracy drops 34% for non-English symptom descriptions",
                "Benchmark shows 34% accuracy drop for Spanish and Mandarin vs English. "
                "Disproportionate clinical impact on non-English-speaking patients.",
                "rai-eval-suite", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(48), components=["diagnosis-engine"]),
    ]),
    findings_batch("batch_medi_preprod_02", "health-ai-scanner", ts(15), "trusted_internal", [
        finding("find_medi_007", "proj_mediassist", "preprod", "security", "moderate",
                "Model inference endpoint rate limiting absent in preprod",
                "No rate limiting on the clinical inference endpoint. Could enable "
                "enumeration attacks against the diagnostic model.",
                "api-security-scanner", "api_security", status="resolved",
                detected_at=ts(15), components=["inference-api"]),
    ]),

    # ── NexusLLM: dev stage, dev→preprod gate pending ────────────────────────
    findings_batch("batch_nexus_dev_01", "internal-pipeline", ts(78), "trusted_internal", [
        finding("find_nexus_001", "proj_nexusllm", "dev", "security", "critical",
                "RAG retriever lacks per-user document access controls — cross-tenant data leak",
                "RAG pipeline does not enforce per-user document isolation. A crafted prompt "
                "can instruct the retriever to surface documents belonging to other users. "
                "This is blocking the dev→preprod promotion gate.",
                "llm-pentest", "dast", status="open", exploitability="medium",
                detected_at=ts(78), components=["rag-retriever", "llm-gateway"]),
        finding("find_nexus_002", "proj_nexusllm", "dev", "security", "critical",
                "Live OpenAI API key committed to main branch",
                "OpenAI API key found in src/config/llm_config.py committed to main. "
                "Key has billing scope and is actively used.",
                "gitleaks", "sast", status="resolved", exploitability="high",
                cwe_ids=["CWE-798"], detected_at=ts(58), components=["llm-gateway"]),
        finding("find_nexus_003", "proj_nexusllm", "dev", "governance", "moderate",
                "No AI-generated content disclosure surfaced to end users",
                "LLM responses are delivered without any disclosure that content is "
                "AI-generated. Violates org RAI transparency policy.",
                "rai-policy-scanner", "rai_monitor", status="open",
                detected_at=ts(40), components=["chat-ui"]),
        finding("find_nexus_004", "proj_nexusllm", "dev", "responsible_ai", "moderate",
                "Hallucination rate 18% on legal clause interpretation — policy threshold 5%",
                "Automated evaluation shows 18% hallucination rate on legal clause tasks. "
                "Org RAI policy requires <5% for regulated-domain applications.",
                "rai-eval-suite", "rai_monitor", status="open", fix_available=False,
                detected_at=ts(30), components=["llm-gateway"]),
        finding("find_nexus_005", "proj_nexusllm", "dev", "security", "low",
                "ChromaDB vector store deployed without encryption at rest",
                "Embeddings can partially reconstruct source document content. "
                "Disk-level encryption not configured.",
                "prowler", "cspm", status="open",
                detected_at=ts(12), components=["vector-store"]),
    ]),
]

# ─────────────────────────────────────────────────────────────────────────────
# APPROVAL CHAINS  (each project has a logical elevation sequence)
# ─────────────────────────────────────────────────────────────────────────────

APPROVALS = [

    # ── FraudShield: fully deployed, ongoing governance ───────────────────────
    # Gate 1: dev → preprod (approved 65 days ago)
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_fraud_dev_preprod",
        "project_id": "proj_fraudshield",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "FraudShield v1.0 promotion dev→preprod — dev critical findings resolved",
        "requested_by": "ci-pipeline@fraudshield",
        "required_roles": ["risk-engineering-lead", "security-lead"],
        "status": "pending",
        "created_at": ts(68),
        "trace_id": "trc_fraud_dev_preprod_v1",
    },
    # Gate 2: preprod → prod (approved 48 days ago)
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_fraud_preprod_prod",
        "project_id": "proj_fraudshield",
        "environment": "prod",
        "request_type": "promotion_gate",
        "trigger": "FraudShield v1.0 production deployment — preprod validation complete",
        "requested_by": "ci-pipeline@fraudshield",
        "required_roles": ["ciso", "risk-engineering-lead", "compliance-officer"],
        "status": "pending",
        "created_at": ts(52),
        "trace_id": "trc_fraud_preprod_prod_v1",
    },
    # Ongoing: threshold change request (pending — governance in action)
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_fraud_threshold_change",
        "project_id": "proj_fraudshield",
        "environment": "prod",
        "request_type": "auth_flow_change",
        "trigger": "Lower fraud decision threshold 0.85→0.78 for Q1 — reduces false positive declines",
        "requested_by": "risk-team@internal",
        "required_roles": ["fraud-risk-lead", "compliance-officer"],
        "status": "pending",
        "created_at": ts(8),
        "trace_id": "trc_fraud_threshold_q1",
    },
    # Exception: RAI fairness finding — accepted risk with conditions
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_fraud_fairness_exception",
        "project_id": "proj_fraudshield",
        "environment": "prod",
        "request_type": "exception",
        "trigger": "180-day exception: demographic disparity finding while fairness remediation programme runs",
        "requested_by": "risk-engineering-lead@internal",
        "required_roles": ["ciso", "chief-risk-officer", "compliance-officer"],
        "status": "pending",
        "created_at": ts(5),
        "trace_id": "trc_fraud_fairness_exc",
    },

    # ── CodePilot: clean fast path, both gates approved ───────────────────────
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_code_dev_preprod",
        "project_id": "proj_codepilot",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "CodePilot v1.0 promotion dev→preprod — all findings resolved",
        "requested_by": "devex-ci@internal",
        "required_roles": ["devex-lead"],
        "status": "pending",
        "created_at": ts(42),
        "trace_id": "trc_code_dev_preprod_v1",
    },
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_code_prod",
        "project_id": "proj_codepilot",
        "environment": "prod",
        "request_type": "deployment_gate",
        "trigger": "CodePilot v1.0 production deployment — internal tool, low risk profile",
        "requested_by": "devex-ci@internal",
        "required_roles": ["devex-lead", "security-lead"],
        "status": "pending",
        "created_at": ts(32),
        "trace_id": "trc_code_prod_v1",
    },

    # ── PriceOracle: preprod, prod gate pending on one open finding ───────────
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_price_dev_preprod",
        "project_id": "proj_priceoracle",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "PriceOracle v3.2 promotion dev→preprod — security findings resolved, legal accepted collusion risk",
        "requested_by": "ml-platform-ci@internal",
        "required_roles": ["ml-platform-lead", "security-lead"],
        "status": "pending",
        "created_at": ts(25),
        "trace_id": "trc_price_dev_preprod_v3",
    },
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_price_preprod_prod",
        "project_id": "proj_priceoracle",
        "environment": "prod",
        "request_type": "promotion_gate",
        "trigger": "PriceOracle v3.2 prod promotion — one open governance finding (data lineage) requires disposition",
        "requested_by": "ml-platform-ci@internal",
        "required_roles": ["ml-platform-lead", "ciso", "compliance-officer"],
        "status": "pending",
        "created_at": ts(4),
        "trace_id": "trc_price_preprod_prod_v3",
    },

    # ── Sentinel: dev gate approved w/ conditions, RAI exception + prod gate pending ──
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_sentinel_dev_preprod",
        "project_id": "proj_sentinel",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "Sentinel v2.3 promotion dev→preprod — security findings resolved, RAI eval required in preprod",
        "requested_by": "platform-security-ci@internal",
        "required_roles": ["security-lead", "rai-reviewer"],
        "status": "pending",
        "created_at": ts(20),
        "trace_id": "trc_sentinel_dev_preprod_v23",
    },
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_sentinel_rai_exception",
        "project_id": "proj_sentinel",
        "environment": "preprod",
        "request_type": "exception",
        "trigger": "Exception request: 60-day window for fairness remediation on facial recognition disparity",
        "requested_by": "platform-security-lead@internal",
        "required_roles": ["ciso", "rai-ethics-board", "vp-engineering"],
        "status": "pending",
        "created_at": ts(10),
        "trace_id": "trc_sentinel_rai_exc_v1",
    },

    # ── MediAssist: prod gate rejected, resubmitted ───────────────────────────
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_medi_dev_preprod",
        "project_id": "proj_mediassist",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "MediAssist v1.0 promotion dev→preprod — dev findings resolved (PHI in dev, audit log retention)",
        "requested_by": "health-ai-ci@internal",
        "required_roles": ["security-lead", "rai-reviewer"],
        "status": "pending",
        "created_at": ts(42),
        "trace_id": "trc_medi_dev_preprod_v1",
    },
    # First prod gate — this one gets REJECTED
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_medi_prod_v1",
        "project_id": "proj_mediassist",
        "environment": "prod",
        "request_type": "deployment_gate",
        "trigger": "MediAssist v1.0 initial production deployment",
        "requested_by": "health-ai-ci@internal",
        "required_roles": ["ciso", "chief-medical-officer", "legal-counsel"],
        "status": "pending",
        "created_at": ts(22),
        "trace_id": "trc_medi_prod_v1",
    },
    # Second prod gate — pending after partial remediation
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_medi_prod_v2",
        "project_id": "proj_mediassist",
        "environment": "prod",
        "request_type": "deployment_gate",
        "trigger": "MediAssist v1.1 production deployment — PHI de-identification implemented, human oversight gate added",
        "requested_by": "health-ai-ci@internal",
        "required_roles": ["ciso", "chief-medical-officer", "legal-counsel"],
        "status": "pending",
        "created_at": ts(5),
        "trace_id": "trc_medi_prod_v2",
    },

    # ── NexusLLM: dev→preprod gate pending, blocked by critical RAG finding ───
    {
        "schema_version": "1.1",
        "approval_request_id": "appr_nexus_dev_preprod",
        "project_id": "proj_nexusllm",
        "environment": "preprod",
        "request_type": "promotion_gate",
        "trigger": "NexusLLM v0.8 promotion dev→preprod — critical RAG data isolation finding must be resolved first",
        "requested_by": "enterprise-ai-ci@internal",
        "required_roles": ["security-lead", "enterprise-ai-lead"],
        "status": "pending",
        "created_at": ts(2),
        "trace_id": "trc_nexus_dev_preprod_v08",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# DECISIONS  (historical — gates that were approved or rejected)
# ─────────────────────────────────────────────────────────────────────────────

DECISIONS = [
    # FraudShield: dev→preprod APPROVED
    {
        "approval_request_id": "appr_fraud_dev_preprod",
        "decision": "approve",
        "decided_by": "raj.kumar@internal",
        "decider_role": "security-lead",
        "decided_at": ts(65),
        "reason": "Both critical dev findings resolved and verified. Preprod load tests passed SLO targets. "
                  "Approved to proceed — full RAI eval required in preprod before prod gate.",
        "trace_id": "trc_fraud_dev_preprod_v1",
    },
    # FraudShield: preprod→prod APPROVED
    {
        "approval_request_id": "appr_fraud_preprod_prod",
        "decision": "approve",
        "decided_by": "sarah.okonkwo@internal",
        "decider_role": "ciso",
        "decided_at": ts(48),
        "reason": "Preprod validation complete. Admin API mTLS enforced. RAI fairness finding acknowledged — "
                  "team to submit formal exception within 30 days. Approved for production.",
        "conditions": [
            "RAI fairness finding (find_fraud_004) must have formal exception or remediation plan within 30 days",
            "FCRA adverse action notice gap (find_fraud_005) to be addressed in next sprint",
        ],
        "trace_id": "trc_fraud_preprod_prod_v1",
    },
    # CodePilot: dev→preprod APPROVED
    {
        "approval_request_id": "appr_code_dev_preprod",
        "decision": "approve",
        "decided_by": "james.okafor@internal",
        "decider_role": "devex-lead",
        "decided_at": ts(38),
        "reason": "All dev findings resolved. Low-risk internal tool. Approved for preprod.",
        "trace_id": "trc_code_dev_preprod_v1",
    },
    # CodePilot: prod APPROVED
    {
        "approval_request_id": "appr_code_prod",
        "decision": "approve",
        "decided_by": "james.okafor@internal",
        "decider_role": "devex-lead",
        "decided_at": ts(28),
        "reason": "Clean preprod run. AI disclosure label added to PR comments. "
                  "Approved — monitor for model drift per open finding find_code_004.",
        "trace_id": "trc_code_prod_v1",
    },
    # PriceOracle: dev→preprod APPROVED
    {
        "approval_request_id": "appr_price_dev_preprod",
        "decision": "approve",
        "decided_by": "lin.wei@internal",
        "decider_role": "ml-platform-lead",
        "decided_at": ts(20),
        "reason": "Security findings resolved. Legal has reviewed and accepted collusion risk finding "
                  "as low probability with existing safeguards. Approved for preprod.",
        "conditions": [
            "Data lineage documentation for v3.2 model to be completed before prod promotion",
        ],
        "trace_id": "trc_price_dev_preprod_v3",
    },
    # Sentinel: dev→preprod APPROVED with conditions
    {
        "approval_request_id": "appr_sentinel_dev_preprod",
        "decision": "approve",
        "decided_by": "maya.patel@internal",
        "decider_role": "rai-reviewer",
        "decided_at": ts(16),
        "reason": "Dev security findings all resolved. Approving promotion to preprod with mandatory "
                  "RAI fairness evaluation before any prod gate is submitted. Demographic disparity "
                  "assessment must be completed in preprod environment.",
        "conditions": [
            "Full RAI fairness evaluation (demographic disparity) must complete before prod gate submission",
            "Biometric consent logging gap must be addressed or have formal exception",
        ],
        "trace_id": "trc_sentinel_dev_preprod_v23",
    },
    # MediAssist: dev→preprod APPROVED
    {
        "approval_request_id": "appr_medi_dev_preprod",
        "decision": "approve",
        "decided_by": "priya.singh@internal",
        "decider_role": "security-lead",
        "decided_at": ts(38),
        "reason": "Dev findings resolved — PHI removed from dev environment, audit log retention corrected. "
                  "Approved for preprod. Comprehensive PHI and SaMD compliance review required before prod.",
        "trace_id": "trc_medi_dev_preprod_v1",
    },
    # MediAssist: first prod gate REJECTED
    {
        "approval_request_id": "appr_medi_prod_v1",
        "decision": "reject",
        "decided_by": "dr.chen@clinical",
        "decider_role": "chief-medical-officer",
        "decided_at": ts(18),
        "reason": "Cannot approve production deployment in current state. Three blocking issues: "
                  "(1) PHI being transmitted to LLM provider without BAA — unacceptable HIPAA risk. "
                  "(2) No human oversight gate before diagnostic suggestions reach clinicians — violates "
                  "our SaMD policy and FDA expectations. (3) No 510(k) pre-submission on record. "
                  "Resubmit when PHI de-identification and oversight gate are implemented.",
        "conditions": [],
        "trace_id": "trc_medi_prod_v1",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS  (discussion threads on key approvals)
# ─────────────────────────────────────────────────────────────────────────────

COMMENTS = [
    # FraudShield threshold change — risk discussion
    ("appr_fraud_threshold_change", {
        "author": "compliance-officer@internal",
        "author_role": "compliance-officer",
        "content": "Before I can sign off on this I need to understand the ECOA exposure. "
                   "If lowering the threshold disproportionately reduces declines for any protected class "
                   "we could argue that's actually correcting the disparity finding. "
                   "Can someone pull the projected demographic impact at 0.78 vs 0.85?",
        "comment_type": "question",
    }),
    ("appr_fraud_threshold_change", {
        "author": "risk-team@internal",
        "author_role": "fraud-risk-lead",
        "content": "Attached projected impact analysis. At 0.78 threshold we see decline rate drop "
                   "from 1.2% to 0.9% overall. The demographic disparity gap narrows from 2.8x to 2.1x "
                   "— still above our 1.5x policy threshold but directionally correct. "
                   "We're treating this change as both a business need and a partial fairness improvement "
                   "while the full remediation programme runs.",
        "comment_type": "evidence",
    }),
    ("appr_fraud_threshold_change", {
        "author": "fraud-risk-lead@internal",
        "author_role": "fraud-risk-lead",
        "content": "Note: this change affects 2.3M daily transactions. We have a 15-minute rollback "
                   "runbook ready and the shadow model (v4.1-beta, find_fraud_007) is already validating "
                   "at 5% traffic so we have a real-world comparison. Recommend approving with monitoring SLA.",
        "comment_type": "note",
        "set_needs_info": False,
    }),

    # FraudShield fairness exception — ethics/legal debate
    ("appr_fraud_fairness_exception", {
        "author": "ciso@internal",
        "author_role": "ciso",
        "content": "180 days is a long window. What's the remediation plan and what are the measurable "
                   "milestones? I need to see a structured programme, not just a time extension.",
        "comment_type": "question",
        "set_needs_info": True,
    }),
    ("appr_fraud_fairness_exception", {
        "author": "risk-engineering-lead@internal",
        "author_role": "risk-engineering-lead",
        "content": "Remediation plan: Q1 — feature audit to remove correlated ZIP-code proxies. "
                   "Q2 — retraining with fairness constraints (Calders-Verwer). Q3 — full RAI "
                   "eval to confirm disparity <1.5x. Milestones logged in JIRA RAI-2024. "
                   "Requesting 180 days to complete this properly without rushing the retraining.",
        "comment_type": "evidence",
    }),

    # PriceOracle prod gate — question on data lineage
    ("appr_price_preprod_prod", {
        "author": "compliance-officer@internal",
        "author_role": "compliance-officer",
        "content": "The open finding find_price_004 (model training data lineage) is marked as "
                   "fix_available=false. What's the plan here? We can't accept that a mission-critical "
                   "partner-facing model has no provenance documentation.",
        "comment_type": "question",
    }),
    ("appr_price_preprod_prod", {
        "author": "ml-platform-lead@internal",
        "author_role": "ml-platform-lead",
        "content": "The training dataset is a licensed third-party dataset (Refinitiv market data). "
                   "We have the license agreement — what was missing was the formal lineage entry in "
                   "our model registry. I've submitted the lineage record this morning. "
                   "Can we proceed with the gate review now?",
        "comment_type": "evidence",
    }),

    # Sentinel RAI exception — ethics board discussion
    ("appr_sentinel_rai_exception", {
        "author": "rai-ethics-board@internal",
        "author_role": "rai-ethics-board",
        "content": "The RAI team has reviewed find_sentinel_003. A 3.2x false-positive disparity "
                   "in security alerts is not something we can grant a blanket exception on — these "
                   "alerts trigger real-world interventions. We need to understand the root cause "
                   "before granting any exception period.",
        "comment_type": "question",
        "set_needs_info": True,
    }),
    ("appr_sentinel_rai_exception", {
        "author": "platform-security-lead@internal",
        "author_role": "platform-security-lead",
        "content": "Root cause analysis complete — the disparity stems from the base YOLOv8 model "
                   "trained predominantly on lighter-skinned faces. We're fine-tuning on a balanced "
                   "dataset and have engaged an external fairness auditor. We're not asking to deploy "
                   "to prod during the exception window — we're asking to continue preprod development "
                   "and evaluation while remediation runs. Prod gate will only be submitted after "
                   "disparity is <1.5x.",
        "comment_type": "evidence",
    }),
    ("appr_sentinel_rai_exception", {
        "author": "vp-engineering@internal",
        "author_role": "vp-engineering",
        "content": "Confirming commitment: we will not submit a prod gate for Sentinel until the RAI "
                   "fairness finding is resolved to below the 1.5x policy threshold. The exception "
                   "covers preprod work only.",
        "comment_type": "note",
    }),

    # MediAssist prod v1 rejection discussion
    ("appr_medi_prod_v1", {
        "author": "health-ai-lead@internal",
        "author_role": "health-ai-lead",
        "content": "Understood. We're implementing PHI de-identification using Microsoft Presidio "
                   "before the LLM prompt is assembled. BAA negotiations with the LLM provider "
                   "are also underway as a parallel track. Timeline for v1.1 resubmission is 3 weeks.",
        "comment_type": "note",
    }),

    # MediAssist prod v2 — progress update
    ("appr_medi_prod_v2", {
        "author": "health-ai-lead@internal",
        "author_role": "health-ai-lead",
        "content": "Resubmitting v1.1 for review. Changes since v1 rejection: "
                   "(1) PHI de-identification via Presidio NER implemented and tested on 10k records. "
                   "(2) Human oversight gate added — all diagnosis suggestions require clinician "
                   "confirmation before appearing in the patient record. "
                   "Open items: 510(k) pre-submission is filed but clearance pending FDA review. "
                   "Multilingual accuracy gap is being addressed in v1.2. Requesting approval "
                   "with conditions on the outstanding items.",
        "comment_type": "evidence",
    }),
    ("appr_medi_prod_v2", {
        "author": "legal-counsel@internal",
        "author_role": "legal-counsel",
        "content": "BAA with LLM provider is executed and on file. "
                   "From a HIPAA perspective the de-identification implementation looks sound — "
                   "we reviewed the Presidio config and it covers all 18 PHI identifiers. "
                   "My remaining concern is the FDA 510(k). Deploying before clearance is "
                   "a regulatory risk we need to formally accept at board level.",
        "comment_type": "question",
        "set_needs_info": True,
    }),

    # NexusLLM dev gate — security team flag
    ("appr_nexus_dev_preprod", {
        "author": "security-lead@internal",
        "author_role": "security-lead",
        "content": "Cannot approve promotion while find_nexus_001 (RAG cross-tenant data isolation) "
                   "is open. This is a critical finding — if exploited in preprod against a shared "
                   "document corpus the blast radius is the entire legal and compliance document set. "
                   "Please resolve and re-raise the gate.",
        "comment_type": "note",
    }),
    ("appr_nexus_dev_preprod", {
        "author": "enterprise-ai-ci@internal",
        "author_role": "enterprise-ai-lead",
        "content": "Acknowledged. We're implementing row-level security in the vector store "
                   "using document owner metadata filters. ETA 5 business days. "
                   "Will re-raise gate once the fix is merged and security team has verified.",
        "comment_type": "evidence",
    }),
]

# ─────────────────────────────────────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────────────────────────────────────

REPORTS = [
    ("proj_fraudshield",  "release_readiness"),
    ("proj_fraudshield",  "residual_risk"),
    ("proj_fraudshield",  "findings_trend"),
    ("proj_codepilot",    "release_readiness"),
    ("proj_priceoracle",  "residual_risk"),
    ("proj_priceoracle",  "control_coverage"),
    ("proj_sentinel",     "rai_posture"),
    ("proj_sentinel",     "residual_risk"),
    ("proj_mediassist",   "rai_posture"),
    ("proj_mediassist",   "release_readiness"),
    ("proj_nexusllm",     "findings_trend"),
    ("proj_nexusllm",     "environment_posture"),
]


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def ok(r: httpx.Response, *ok_codes) -> bool:
    return r.status_code in (ok_codes or (200, 201, 202))


def main(api_url: str) -> None:
    print(f"\n  PeaRL Demo Seed  →  {api_url}\n")

    anon = httpx.Client(base_url=api_url, timeout=30)
    auth = httpx.Client(base_url=api_url, timeout=30, headers={"X-API-Key": API_KEY})

    with anon, auth:

        # ── Projects ──────────────────────────────────────────────────────────
        print("── 1/6  Projects ─────────────────────────────────────────────")
        for p in PROJECTS:
            r = anon.post("/api/v1/projects", json=p)
            if r.status_code == 201:
                print(f"  ✓  {p['project_id']:22}  {p['name']}")
            elif r.status_code == 409:
                print(f"  ~  {p['project_id']:22}  already exists")
            else:
                print(f"  ✗  {p['project_id']:22}  {r.status_code}: {r.text[:100]}")

        # ── Findings ──────────────────────────────────────────────────────────
        print("\n── 2/6  Findings ─────────────────────────────────────────────")
        for batch in FINDINGS_BATCHES:
            proj = batch["findings"][0]["project_id"]
            n = len(batch["findings"])
            r = anon.post("/api/v1/findings/ingest", json=batch)
            if ok(r):
                print(f"  ✓  {proj:22}  {n} findings")
            elif r.status_code == 500 and "duplicate" in r.text.lower():
                print(f"  ~  {proj:22}  already ingested")
            else:
                print(f"  ✗  {proj:22}  {r.status_code}: {r.text[:100]}")

        # ── Approval requests ─────────────────────────────────────────────────
        print("\n── 3/6  Approval Requests ────────────────────────────────────")
        for a in APPROVALS:
            r = anon.post("/api/v1/approvals/requests", json=a)
            if ok(r):
                label = f"[{a['environment']}] {a['request_type']}"
                print(f"  ✓  {a['approval_request_id']:30}  {label}")
            elif r.status_code == 409:
                print(f"  ~  {a['approval_request_id']:30}  already exists")
            else:
                print(f"  ✗  {a['approval_request_id']:30}  {r.status_code}: {r.text[:100]}")

        # ── Decisions ─────────────────────────────────────────────────────────
        print("\n── 4/6  Decisions ────────────────────────────────────────────")
        for d in DECISIONS:
            aid = d["approval_request_id"]
            body = {"schema_version": "1.1", **d}
            r = auth.post(f"/api/v1/approvals/{aid}/decide", json=body)
            if ok(r):
                verb = "APPROVED ✓" if d["decision"] == "approve" else "REJECTED ✗"
                print(f"  {verb:12}  {aid}")
            else:
                print(f"  ✗  {aid}  {r.status_code}: {r.text[:100]}")

        # ── Comments ──────────────────────────────────────────────────────────
        print("\n── 5/6  Comments ─────────────────────────────────────────────")
        comment_counts: dict[str, int] = {}
        for (aid, body) in COMMENTS:
            r = auth.post(f"/api/v1/approvals/{aid}/comments", json=body)
            if ok(r):
                comment_counts[aid] = comment_counts.get(aid, 0) + 1
            else:
                print(f"  ✗  {aid}  {r.status_code}: {r.text[:100]}")
        for aid, count in comment_counts.items():
            print(f"  ✓  {aid:30}  {count} comment{'s' if count > 1 else ''}")

        # ── Reports ───────────────────────────────────────────────────────────
        print("\n── 6/6  Reports ──────────────────────────────────────────────")
        for (proj_id, rtype) in REPORTS:
            r = anon.post(f"/api/v1/projects/{proj_id}/reports/generate", json={
                "schema_version": "1.1",
                "report_type": rtype,
                "format": "json",
            })
            if ok(r):
                print(f"  ✓  {proj_id:22}  {rtype}")
            else:
                print(f"  ✗  {proj_id}/{rtype}  {r.status_code}: {r.text[:100]}")

    print("""
── Summary ───────────────────────────────────────────────────
  PRODUCTION   FraudShield  ✓ live   CodePilot ✓ live
  PREPROD→PROD PriceOracle  gate pending (data lineage finding)
  PREPROD      Sentinel     RAI exception in flight (fairness)
               MediAssist   prod v1 rejected → v2 pending review
  DEV→PREPROD  NexusLLM     gate pending (critical RAG finding)

  Dashboard → http://localhost:5177
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()
    main(args.api_url)
