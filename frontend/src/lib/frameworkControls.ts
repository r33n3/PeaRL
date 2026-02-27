/** Compliance framework control catalogue for gate rule picker and evaluation. */

export interface ControlMeta {
  label: string;
  evidenceType: "attestation" | "scan_result" | "artifact" | "derived";
  description?: string;
}

export interface FrameworkCategory {
  label: string;
  controls: Record<string, ControlMeta>;
}

export interface FrameworkDef {
  label: string;
  description: string;
  aiOnly?: boolean;
  categories: Record<string, FrameworkCategory>;
}

// ── AIUC-1 helper — same logic as fieldKeyToAiuc1Label in SettingsPage ────────
export function aiuc1ControlLabel(key: string): string {
  const m = key.match(/^([a-f])(\d{3})_(\d+)_(.+)$/);
  if (!m) return key;
  const [, prefix, num, sub, rest] = m;
  const name = rest!.replace(/_/g, " ");
  return `${prefix!.toUpperCase()}${num}.${sub}: ${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}

function aiuc1Controls(keys: string[]): Record<string, ControlMeta> {
  return Object.fromEntries(
    keys.map((k) => [k, { label: aiuc1ControlLabel(k), evidenceType: "attestation" as const }]),
  );
}

// ── Framework catalogue ────────────────────────────────────────────────────────
export const FRAMEWORK_CONTROLS: Record<string, FrameworkDef> = {
  // ── AIUC-1 ──────────────────────────────────────────────────────────────────
  aiuc1: {
    label: "AIUC-1",
    description: "AI Use Case Controls — governance attestation framework",
    aiOnly: true,
    categories: {
      data_privacy: {
        label: "A. Data & Privacy",
        controls: aiuc1Controls([
          "a001_1_policy_documentation",
          "a001_2_data_retention_implementation",
          "a001_3_data_subject_right_processes",
          "a002_1_output_usage_ownership_policy",
          "a003_1_data_collection_scoping",
          "a003_2_alerting_for_auth_failures",
          "a003_3_authorization_system_integration",
          "a004_1_user_guidance_on_confidential_info",
          "a004_2_foundational_model_ip_protections",
          "a004_3_ip_detection_implementation",
          "a004_4_ip_disclosure_monitoring",
          "a005_1_consent_for_combined_data",
          "a005_2_customer_data_isolation",
          "a005_3_privacy_enhancing_controls",
          "a006_1_pii_detection_filtering",
          "a006_2_pii_access_controls",
          "a006_3_dlp_system_integration",
          "a007_1_model_provider_ip_protections",
          "a007_2_ip_infringement_filtering",
          "a007_3_user_facing_ip_notices",
        ]),
      },
      security: {
        label: "B. Security",
        controls: aiuc1Controls([
          "b001_1_adversarial_testing_report",
          "b001_2_security_program_integration",
          "b002_1_adversarial_input_detection_alerting",
          "b002_2_adversarial_incident_response",
          "b002_3_detection_config_updates",
          "b002_4_preprocessing_adversarial_detection",
          "b002_5_ai_security_alerts",
          "b003_1_technical_disclosure_guidelines",
          "b003_2_public_disclosure_approval_records",
          "b004_1_anomalous_usage_detection",
          "b004_2_rate_limits",
          "b004_3_external_pentest_ai_endpoints",
          "b004_4_vulnerability_remediation",
          "b005_1_input_filtering",
          "b005_2_input_moderation_approach",
          "b005_3_warning_for_blocked_inputs",
          "b005_4_input_filtering_logs",
          "b005_5_input_filter_performance",
          "b006_1_agent_service_access_restrictions",
          "b006_2_agent_security_monitoring_alerting",
          "b007_1_user_access_controls",
          "b007_2_access_reviews",
          "b008_1_model_access_controls",
          "b008_2_api_deployment_security",
          "b008_3_model_hosting_security",
          "b008_4_model_integrity_verification",
          "b009_1_output_volume_limits",
          "b009_2_user_output_notices",
          "b009_3_output_precision_controls",
        ]),
      },
      safety: {
        label: "C. Safety",
        controls: aiuc1Controls([
          "c001_1_risk_taxonomy",
          "c001_2_risk_taxonomy_reviews",
          "c002_1_pre_deployment_test_approval",
          "c002_2_sdlc_integration",
          "c002_3_vulnerability_scan_results",
          "c003_1_harmful_output_filtering",
          "c003_2_guardrails_for_high_risk_advice",
          "c003_3_guardrails_for_biased_outputs",
          "c003_4_filtering_performance_benchmarks",
          "c004_1_out_of_scope_guardrails",
          "c004_2_out_of_scope_attempt_logs",
          "c004_3_user_guidance_on_scope",
          "c005_1_risk_detection_response",
          "c005_2_human_review_workflows",
          "c005_3_automated_response_mechanisms",
          "c006_1_output_sanitization",
          "c006_2_warning_labels_untrusted_content",
          "c006_3_adversarial_output_detection",
          "c007_1_high_risk_criteria_definition",
          "c007_2_high_risk_detection_mechanisms",
          "c007_3_human_review_for_high_risk",
          "c008_1_risk_monitoring_logs",
          "c008_2_monitoring_findings_documentation",
          "c008_4_security_tooling_integration",
          "c009_1_user_intervention_mechanisms",
          "c009_2_feedback_intervention_reviews",
          "c010_1_harmful_output_testing_report",
          "c011_1_outofscope_output_testing_report",
          "c012_1_customer_risk_testing_report",
        ]),
      },
      reliability: {
        label: "D. Reliability",
        controls: aiuc1Controls([
          "d001_1_groundedness_filter",
          "d001_2_user_citations_source_attribution",
          "d001_3_user_uncertainty_labels",
          "d002_1_hallucination_testing_report",
          "d003_1_tool_authorization_validation",
          "d003_2_rate_limits_for_tools",
          "d003_3_tool_call_log",
          "d003_4_human_approval_workflows",
          "d003_5_tool_call_log_reviews",
          "d004_1_tool_call_testing_report",
        ]),
      },
      accountability: {
        label: "E. Accountability",
        controls: aiuc1Controls([
          "e001_1_security_breach_failure_plan",
          "e002_1_harmful_output_failure_plan",
          "e002_2_harmful_output_failure_procedures",
          "e003_1_hallucination_failure_plan",
          "e003_2_hallucination_failure_procedures",
          "e004_1_change_approval_policy_records",
          "e004_2_code_signing_implementation",
          "e005_1_deployment_decisions",
          "e006_1_vendor_due_diligence",
          "e008_1_internal_review_documentation",
          "e008_2_external_feedback_integration",
          "e009_1_third_party_access_monitoring",
          "e010_1_acceptable_use_policy",
          "e010_2_aup_violation_detection",
          "e010_3_user_notification_for_aup_breaches",
          "e010_4_guardrails_enforcing_acceptable_use",
          "e011_1_ai_processing_locations",
          "e011_2_data_transfer_compliance",
          "e012_1_regulatory_compliance_reviews",
          "e013_1_quality_objectives_risk_management",
          "e013_2_change_management_procedures",
          "e013_3_issue_tracking_monitoring",
          "e013_4_data_management_procedures",
          "e013_5_stakeholder_communication_procedures",
          "e015_1_logging_implementation",
          "e015_2_log_storage",
          "e015_3_log_integrity_protection",
          "e016_1_text_ai_disclosure",
          "e016_2_voice_ai_disclosure",
          "e016_3_labelling_ai_generated_content",
          "e016_4_automation_ai_disclosure",
          "e016_5_system_response_to_ai_inquiry",
          "e017_1_transparency_policy",
          "e017_2_model_cards_system_documentation",
          "e017_3_transparency_report_sharing_policy",
        ]),
      },
      society: {
        label: "F. Society",
        controls: aiuc1Controls([
          "f001_1_foundation_model_cyber_capabilities",
          "f001_2_cyber_use_detection",
          "f002_1_foundation_model_cbrn_capabilities",
          "f002_2_catastrophic_misuse_monitoring",
        ]),
      },
    },
  },

  // ── OWASP LLM Top 10 ─────────────────────────────────────────────────────────
  owasp_llm: {
    label: "OWASP LLM Top 10",
    description: "Top 10 security risks for LLM applications (2025 edition)",
    aiOnly: true,
    categories: {
      llm_top10: {
        label: "LLM Top 10 Risks",
        controls: {
          llm01_prompt_injection: {
            label: "LLM01: Prompt Injection",
            evidenceType: "scan_result",
            description: "Attackers manipulate the LLM via crafted inputs to override instructions or exfiltrate data",
          },
          llm02_insecure_output_handling: {
            label: "LLM02: Insecure Output Handling",
            evidenceType: "scan_result",
            description: "Downstream components process LLM output without sufficient validation (XSS, SSRF, RCE risk)",
          },
          llm03_training_data_poisoning: {
            label: "LLM03: Training Data Poisoning",
            evidenceType: "attestation",
            description: "Training or fine-tuning data manipulated to introduce backdoors or biases",
          },
          llm04_model_denial_of_service: {
            label: "LLM04: Model Denial of Service",
            evidenceType: "derived",
            description: "Resource exhaustion via adversarial inputs, recursive context, or excessive requests",
          },
          llm05_supply_chain_vulnerabilities: {
            label: "LLM05: Supply Chain Vulnerabilities",
            evidenceType: "artifact",
            description: "Compromised pre-trained models, plugins, or third-party training data",
          },
          llm06_sensitive_info_disclosure: {
            label: "LLM06: Sensitive Info Disclosure",
            evidenceType: "scan_result",
            description: "LLM reveals confidential data, PII, or proprietary system details in outputs",
          },
          llm07_insecure_plugin_design: {
            label: "LLM07: Insecure Plugin Design",
            evidenceType: "scan_result",
            description: "LLM plugins lack authorization, input sanitization, or output validation",
          },
          llm08_excessive_agency: {
            label: "LLM08: Excessive Agency",
            evidenceType: "attestation",
            description: "LLM granted more permissions, autonomy, or tool access than needed",
          },
          llm09_overreliance: {
            label: "LLM09: Overreliance",
            evidenceType: "attestation",
            description: "Users or systems rely on LLM output without adequate verification mechanisms",
          },
          llm10_model_theft: {
            label: "LLM10: Model Theft",
            evidenceType: "derived",
            description: "Unauthorized extraction or replication of proprietary model via inference API",
          },
        },
      },
    },
  },

  // ── OWASP Web Top 10 ─────────────────────────────────────────────────────────
  owasp_web: {
    label: "OWASP Web Top 10",
    description: "Top 10 web application security risks (2021) — applies to generated web code",
    categories: {
      web_top10: {
        label: "Web Top 10 Risks",
        controls: {
          a01_broken_access_control: {
            label: "A01: Broken Access Control",
            evidenceType: "scan_result",
            description: "Authenticated user restrictions not properly enforced; privilege escalation risk",
          },
          a02_cryptographic_failures: {
            label: "A02: Cryptographic Failures",
            evidenceType: "scan_result",
            description: "Weak or missing cryptography exposing sensitive data in transit or at rest",
          },
          a03_injection: {
            label: "A03: Injection",
            evidenceType: "scan_result",
            description: "SQL, NoSQL, LDAP, OS command injection in generated or reviewed code",
          },
          a04_insecure_design: {
            label: "A04: Insecure Design",
            evidenceType: "derived",
            description: "Missing or ineffective security controls in the application design",
          },
          a05_security_misconfiguration: {
            label: "A05: Security Misconfiguration",
            evidenceType: "scan_result",
            description: "Insecure defaults, unnecessary features enabled, missing hardening",
          },
          a06_vulnerable_components: {
            label: "A06: Vulnerable & Outdated Components",
            evidenceType: "scan_result",
            description: "Using libraries or frameworks with known CVEs",
          },
          a07_auth_failures: {
            label: "A07: Identification & Auth Failures",
            evidenceType: "scan_result",
            description: "Broken authentication allowing account compromise or session hijacking",
          },
          a08_software_integrity_failures: {
            label: "A08: Software & Data Integrity Failures",
            evidenceType: "artifact",
            description: "Code or infrastructure deployed without integrity verification or signing",
          },
          a09_logging_monitoring_failures: {
            label: "A09: Security Logging & Monitoring Failures",
            evidenceType: "derived",
            description: "Insufficient logging and alerting allowing breaches to go undetected",
          },
          a10_ssrf: {
            label: "A10: Server-Side Request Forgery",
            evidenceType: "scan_result",
            description: "Server fetches remote resources at attacker-controlled URLs",
          },
        },
      },
    },
  },

  // ── MITRE ATLAS ──────────────────────────────────────────────────────────────
  mitre_atlas: {
    label: "MITRE ATLAS",
    description: "Adversarial Threat Landscape for AI Systems — AI analog to ATT&CK",
    aiOnly: true,
    categories: {
      reconnaissance: {
        label: "Reconnaissance",
        controls: {
          aml_t0000_phishing_for_ml_info: {
            label: "AML.T0000: Phishing for ML Info",
            evidenceType: "attestation",
            description: "Social engineering to gather ML system architecture details",
          },
          aml_t0001_discover_ml_artifacts: {
            label: "AML.T0001: Discover ML Artifacts",
            evidenceType: "derived",
            description: "Identify exposed ML-related artifacts in the target environment",
          },
        },
      },
      ml_attack_staging: {
        label: "ML Attack Staging",
        controls: {
          aml_t0016_obtain_capabilities: {
            label: "AML.T0016: Obtain Capabilities",
            evidenceType: "attestation",
            description: "Acquire ML tools or models to support downstream attacks",
          },
          aml_t0051_supply_chain_compromise: {
            label: "AML.T0051: Supply Chain Compromise",
            evidenceType: "artifact",
            description: "Compromise pre-trained model, plugin, or ML pipeline component",
          },
        },
      },
      initial_access: {
        label: "Initial Access",
        controls: {
          aml_t0012_valid_accounts: {
            label: "AML.T0012: Valid Accounts",
            evidenceType: "scan_result",
            description: "Use of legitimate credentials to access ML systems or APIs",
          },
        },
      },
      ml_model_access: {
        label: "ML Model Access",
        controls: {
          aml_t0040_inference_api_access: {
            label: "AML.T0040: ML Inference API Access",
            evidenceType: "derived",
            description: "Adversarial queries via public or internal inference API",
          },
          aml_t0043_craft_adversarial_data: {
            label: "AML.T0043: Craft Adversarial Data",
            evidenceType: "attestation",
            description: "Inputs crafted to cause model misclassification or unsafe outputs",
          },
        },
      },
      exfiltration: {
        label: "Exfiltration",
        controls: {
          aml_t0057_llm_prompt_injection: {
            label: "AML.T0057: LLM Prompt Injection",
            evidenceType: "scan_result",
            description: "Prompt injection used to exfiltrate data or override system behavior",
          },
          aml_t0024_exfiltration_via_ml_inference: {
            label: "AML.T0024: Exfiltration via ML Inference",
            evidenceType: "derived",
            description: "Extract training data by exploiting model memorization via repeated queries",
          },
        },
      },
      impact: {
        label: "Impact",
        controls: {
          aml_t0029_denial_of_ml_service: {
            label: "AML.T0029: Denial of ML Service",
            evidenceType: "derived",
            description: "Degrade or deny availability of ML service through adversarial inputs",
          },
          aml_t0031_erode_model_integrity: {
            label: "AML.T0031: Erode ML Model Integrity",
            evidenceType: "attestation",
            description: "Gradual poisoning to alter model behavior in production over time",
          },
        },
      },
    },
  },

  // ── SLSA ─────────────────────────────────────────────────────────────────────
  slsa: {
    label: "SLSA",
    description: "Supply-chain Levels for Software Artifacts — code provenance & integrity",
    categories: {
      provenance: {
        label: "Build Provenance",
        controls: {
          level_1: {
            label: "Level 1: Provenance Exists",
            evidenceType: "artifact",
            description: "Build process produces a signed provenance artifact",
          },
          level_2: {
            label: "Level 2: Hosted Build",
            evidenceType: "artifact",
            description: "Build runs on a hosted, parameterized CI/CD system",
          },
          level_3: {
            label: "Level 3: Hardened Build",
            evidenceType: "artifact",
            description: "Isolated, ephemeral, non-falsifiable build environment",
          },
        },
      },
      artifacts: {
        label: "Artifact Integrity",
        controls: {
          sbom_generated: {
            label: "SBOM Generated",
            evidenceType: "artifact",
            description: "Software Bill of Materials produced for every build",
          },
          artifact_signed: {
            label: "Artifact Signed",
            evidenceType: "artifact",
            description: "Build output cryptographically signed and verifiable",
          },
        },
      },
      dependencies: {
        label: "Dependency Review",
        controls: {
          dependency_review: {
            label: "Dependency Review Completed",
            evidenceType: "scan_result",
            description: "SCA scan run on all direct and transitive dependencies",
          },
          no_critical_cves: {
            label: "No Critical CVEs",
            evidenceType: "scan_result",
            description: "No critical-severity CVEs in the dependency tree",
          },
          license_cleared: {
            label: "Licenses Cleared",
            evidenceType: "derived",
            description: "No GPL/copyleft conflicts in the dependency license tree",
          },
        },
      },
    },
  },

  // ── NIST AI RMF ──────────────────────────────────────────────────────────────
  nist_rmf: {
    label: "NIST AI RMF",
    description: "AI Risk Management Framework — Govern, Map, Measure, Manage",
    aiOnly: true,
    categories: {
      govern: {
        label: "Govern",
        controls: {
          policy_defined: {
            label: "AI Risk Policy Defined",
            evidenceType: "attestation",
            description: "Organizational AI risk policies documented, approved, and current",
          },
          roles_defined: {
            label: "Accountability Roles Defined",
            evidenceType: "attestation",
            description: "AI risk accountability and ownership roles formally assigned",
          },
          oversight_mechanism: {
            label: "Oversight Mechanism Established",
            evidenceType: "derived",
            description: "Human oversight process in place for consequential AI decisions",
          },
        },
      },
      map: {
        label: "Map",
        controls: {
          risk_categorized: {
            label: "AI Risk Categorized",
            evidenceType: "attestation",
            description: "AI use case categorized by risk level, domain, and affected populations",
          },
          threat_assessment: {
            label: "Threat & Vulnerability Assessment",
            evidenceType: "derived",
            description: "AI-specific threats and vulnerabilities identified and documented",
          },
          context_established: {
            label: "Deployment Context Established",
            evidenceType: "attestation",
            description: "Deployment environment, user base, and affected stakeholders documented",
          },
        },
      },
      measure: {
        label: "Measure",
        controls: {
          metrics_defined: {
            label: "AI Risk Metrics Defined",
            evidenceType: "attestation",
            description: "Quantitative metrics for AI performance, accuracy, and risk established",
          },
          monitoring_plan: {
            label: "AI Monitoring Plan",
            evidenceType: "derived",
            description: "Continuous monitoring plan for AI behavior in production documented",
          },
          bias_evaluated: {
            label: "Bias & Fairness Evaluated",
            evidenceType: "artifact",
            description: "Formal bias and fairness evaluation completed with documented results",
          },
        },
      },
      manage: {
        label: "Manage",
        controls: {
          incident_plan: {
            label: "AI Incident Response Plan",
            evidenceType: "attestation",
            description: "Documented and tested plan for responding to AI failures and incidents",
          },
          risk_treatment: {
            label: "Risk Treatment Actions Defined",
            evidenceType: "derived",
            description: "Specific risk mitigations selected, implemented, and tracked",
          },
          rollback_plan: {
            label: "Model Rollback Plan",
            evidenceType: "attestation",
            description: "Procedure for reverting to a prior stable model version on failure",
          },
        },
      },
    },
  },

  // ── NIST SSDF ────────────────────────────────────────────────────────────────
  ssdf: {
    label: "NIST SSDF",
    description: "Secure Software Development Framework (NIST SP 800-218)",
    categories: {
      prepare: {
        label: "Prepare the Organization (PO)",
        controls: {
          po1_security_requirements: {
            label: "PO.1: Security Requirements",
            evidenceType: "attestation",
            description: "Security requirements defined and maintained for all software development",
          },
          po2_roles_responsibilities: {
            label: "PO.2: Roles & Responsibilities",
            evidenceType: "attestation",
            description: "Security roles, responsibilities, and training requirements assigned",
          },
          po3_third_party_management: {
            label: "PO.3: Third-Party Management",
            evidenceType: "derived",
            description: "Third-party software components and services managed securely",
          },
        },
      },
      produce: {
        label: "Produce Well-Secured Software (PW)",
        controls: {
          pw1_security_design: {
            label: "PW.1: Security Design",
            evidenceType: "attestation",
            description: "Security considered in architecture and design (threat model, secure patterns)",
          },
          pw2_threat_modeling: {
            label: "PW.2: Threat Modeling",
            evidenceType: "artifact",
            description: "Formal threat model produced, reviewed, and used to inform controls",
          },
          pw4_reusable_components: {
            label: "PW.4: Reusable Secure Components",
            evidenceType: "derived",
            description: "Hardened, vetted reusable components used where available",
          },
          pw5_secure_defaults: {
            label: "PW.5: Secure Defaults",
            evidenceType: "derived",
            description: "Software configured securely by default; opt-in for less-secure options",
          },
          pw6_code_review: {
            label: "PW.6: Code Review",
            evidenceType: "derived",
            description: "Security-focused peer or automated code review performed before merge",
          },
          pw7_security_testing: {
            label: "PW.7: Security Testing",
            evidenceType: "scan_result",
            description: "SAST, DAST, and/or fuzzing run on the codebase",
          },
          pw8_vulnerability_scanning: {
            label: "PW.8: Vulnerability Scanning",
            evidenceType: "scan_result",
            description: "Automated vulnerability scanning integrated into CI/CD pipeline",
          },
        },
      },
      respond: {
        label: "Respond to Vulnerabilities (RV)",
        controls: {
          rv1_disclosure_process: {
            label: "RV.1: Vulnerability Disclosure Process",
            evidenceType: "attestation",
            description: "Process for receiving, tracking, and disclosing vulnerabilities defined",
          },
          rv2_root_cause_analysis: {
            label: "RV.2: Root Cause Analysis",
            evidenceType: "derived",
            description: "Root causes of vulnerabilities identified and used to prevent recurrence",
          },
          rv3_remediation: {
            label: "RV.3: Remediation of Vulnerabilities",
            evidenceType: "derived",
            description: "Vulnerabilities addressed and tracked to closure in a timely manner",
          },
        },
      },
    },
  },
};
