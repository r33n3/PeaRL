import { useState, useEffect, useMemo } from "react";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { MonoText } from "@/components/shared/MonoText";
import {
  useGates,
  useUpdateGateRules,
  useUpdateGateApprovalMode,
  useCreateGate,
  useDeleteGate,
  GATE_RULE_TYPES,
} from "@/api/promotions";
import type { GateData, GateRuleData } from "@/api/promotions";
import {
  useIntegrations,
  useCreateIntegration,
  useDeleteIntegration,
  useTestIntegration,
} from "@/api/integrations";
import { useOrgBaseline, useSaveOrgBaseline } from "@/api/settings";
import { useDefaultPipeline, useUpdatePipeline } from "@/api/pipelines";
import type { PipelineStage } from "@/api/pipelines";
import { useProjects } from "@/api/dashboard";
import type { IntegrationEndpoint } from "@/lib/types";
import {
  Plug,
  ShieldCheck,
  FileCode,
  Bell,
  RefreshCw,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Plus,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Minus,
  Save,
  Edit2,
  Info,
  Loader2,
  Layers,
  ArrowRight,
  ChevronUp,
  AlertTriangle,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Tab = "integrations" | "gates" | "baseline" | "notifications" | "environments";

const TABS: { key: Tab; icon: typeof Plug; label: string }[] = [
  { key: "integrations", icon: Plug, label: "Integrations" },
  { key: "gates", icon: ShieldCheck, label: "Gate Rules" },
  { key: "baseline", icon: FileCode, label: "Org Baseline" },
  { key: "notifications", icon: Bell, label: "Notifications" },
  { key: "environments", icon: Layers, label: "Environments" },
];

const ADAPTER_TYPES = [
  "snyk",
  "semgrep",
  "trivy",
  "slack",
  "jira",
  "github",
] as const;

const INTEGRATION_TYPES = ["source", "sink", "bidirectional"] as const;

const EVENT_TYPES = [
  "approval.created",
  "approval.decided",
  "approval.needs_info",
  "promotion.completed",
  "finding.critical_detected",
  "cost.threshold_reached",
] as const;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** snake_case -> Title Case */
function humanize(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Project Selector                                                   */
/* ------------------------------------------------------------------ */

function ProjectSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const { data: projects, isLoading } = useProjects();

  useEffect(() => {
    const first = projects?.[0];
    if (!value && first) {
      onChange(first.project_id);
    }
  }, [projects, value, onChange]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono">
        <Loader2 size={14} className="animate-spin" /> Loading projects...
      </div>
    );
  }

  if (!projects || projects.length === 0) {
    return (
      <span className="text-bone-dim text-sm font-mono">
        No projects available
      </span>
    );
  }

  return (
    <select
      className="input-vault text-sm w-64"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {projects.map((p) => (
        <option key={p.project_id} value={p.project_id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}

/* ================================================================== */
/*  TAB 1 -- Integrations                                             */
/* ================================================================== */

interface NewIntegrationForm {
  name: string;
  adapter_type: string;
  integration_type: string;
  category: string;
  base_url: string;
}

const EMPTY_FORM: NewIntegrationForm = {
  name: "",
  adapter_type: "snyk",
  integration_type: "source",
  category: "",
  base_url: "",
};

function IntegrationsTab() {
  const [projectId, setProjectId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NewIntegrationForm>({ ...EMPTY_FORM });
  const [testResults, setTestResults] = useState<
    Record<string, { success: boolean; message?: string }>
  >({});

  const { data: integrations, isLoading } = useIntegrations(projectId);
  const createMut = useCreateIntegration();
  const deleteMut = useDeleteIntegration();
  const testMut = useTestIntegration();

  const handleCreate = () => {
    if (!projectId || !form.name || !form.base_url) return;
    createMut.mutate(
      { projectId, data: form },
      {
        onSuccess: () => {
          setForm({ ...EMPTY_FORM });
          setShowForm(false);
        },
      }
    );
  };

  const handleDelete = (ep: IntegrationEndpoint) => {
    if (!window.confirm(`Delete integration "${ep.name}"?`)) return;
    deleteMut.mutate({ projectId, endpointId: ep.endpoint_id });
  };

  const handleTest = (ep: IntegrationEndpoint) => {
    testMut.mutate(
      { projectId, endpointId: ep.endpoint_id },
      {
        onSuccess: (result) => {
          setTestResults((prev) => ({
            ...prev,
            [ep.endpoint_id]: result as { success: boolean; message?: string },
          }));
          setTimeout(() => {
            setTestResults((prev) => {
              const next = { ...prev };
              delete next[ep.endpoint_id];
              return next;
            });
          }, 3000);
        },
        onError: () => {
          setTestResults((prev) => ({
            ...prev,
            [ep.endpoint_id]: { success: false, message: "Connection failed" },
          }));
          setTimeout(() => {
            setTestResults((prev) => {
              const next = { ...prev };
              delete next[ep.endpoint_id];
              return next;
            });
          }, 3000);
        },
      }
    );
  };

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <ProjectSelector value={projectId} onChange={setProjectId} />
        <button
          className="btn-teal flex items-center gap-1.5 text-sm"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus size={14} />
          Add Integration
        </button>
      </div>

      {/* Inline add form */}
      {showForm && (
        <VaultCard className="space-y-3">
          <h3 className="vault-heading text-xs mb-2">New Integration</h3>
          <div className="grid grid-cols-2 gap-3">
            <input
              className="input-vault text-sm"
              placeholder="Name"
              value={form.name}
              onChange={(e) =>
                setForm((f) => ({ ...f, name: e.target.value }))
              }
            />
            <select
              className="input-vault text-sm"
              value={form.adapter_type}
              onChange={(e) =>
                setForm((f) => ({ ...f, adapter_type: e.target.value }))
              }
            >
              {ADAPTER_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              className="input-vault text-sm"
              value={form.integration_type}
              onChange={(e) =>
                setForm((f) => ({ ...f, integration_type: e.target.value }))
              }
            >
              {INTEGRATION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className="input-vault text-sm"
              placeholder="Category"
              value={form.category}
              onChange={(e) =>
                setForm((f) => ({ ...f, category: e.target.value }))
              }
            />
          </div>
          <input
            className="input-vault text-sm w-full"
            placeholder="Base URL (https://...)"
            value={form.base_url}
            onChange={(e) =>
              setForm((f) => ({ ...f, base_url: e.target.value }))
            }
          />
          <div className="flex gap-2 pt-1">
            <button
              className="btn-teal text-sm flex items-center gap-1.5"
              disabled={createMut.isPending || !form.name || !form.base_url}
              onClick={handleCreate}
            >
              {createMut.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Plus size={14} />
              )}
              Create
            </button>
            <button
              className="btn-ghost text-sm"
              onClick={() => {
                setShowForm(false);
                setForm({ ...EMPTY_FORM });
              }}
            >
              Cancel
            </button>
          </div>
        </VaultCard>
      )}

      {/* List */}
      {!projectId ? (
        <VaultCard className="text-center py-8">
          <p className="text-bone-dim font-mono text-sm">
            Select a project to view integrations
          </p>
        </VaultCard>
      ) : isLoading ? (
        <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-6 justify-center">
          <Loader2 size={16} className="animate-spin" /> Loading integration
          endpoints...
        </div>
      ) : !integrations || integrations.length === 0 ? (
        <VaultCard className="text-center py-8">
          <Plug size={24} className="text-bone-dim mx-auto mb-2" />
          <p className="text-bone-dim font-mono text-sm">
            No integrations configured
          </p>
          <p className="text-bone-dim font-mono text-xs mt-1">
            Click "Add Integration" to register an endpoint
          </p>
        </VaultCard>
      ) : (
        <div className="space-y-3">
          {integrations.map((ep) => (
            <VaultCard
              key={ep.endpoint_id}
              className="flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    ep.enabled ? "bg-cold-teal" : "bg-dried-blood-bright"
                  }`}
                />
                <div>
                  <span className="text-sm text-bone font-heading font-semibold">
                    {ep.name}
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <MonoText className="text-xs">{ep.adapter_type}</MonoText>
                    <span className="text-[10px] text-clinical-cyan bg-charcoal px-1.5 py-0.5 rounded font-mono">
                      {ep.integration_type}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Test result inline */}
                {(() => {
                  const tr = testResults[ep.endpoint_id];
                  if (!tr) return null;
                  return (
                    <span
                      className={`text-xs font-mono ${
                        tr.success ? "text-cold-teal" : "text-dried-blood-bright"
                      }`}
                    >
                      {tr.success ? "Connected" : tr.message || "Failed"}
                    </span>
                  );
                })()}
                <button
                  className="btn-ghost text-xs py-1 px-2 flex items-center gap-1"
                  onClick={() => handleTest(ep)}
                  disabled={testMut.isPending}
                >
                  <RefreshCw
                    size={12}
                    className={testMut.isPending ? "animate-spin" : ""}
                  />
                  Test
                </button>
                <button
                  className="btn-ghost text-xs py-1 px-2 text-dried-blood-bright flex items-center gap-1"
                  onClick={() => handleDelete(ep)}
                  disabled={deleteMut.isPending}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </VaultCard>
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  TAB 2 -- Gate Rules                                               */
/* ================================================================== */

interface LocalGateState {
  rules: (GateRuleData & { _enabled: boolean; _threshold?: number | null })[];
  dirty: boolean;
}

/** AIUC-1 sub-control keys grouped by domain category (matches org-baseline schema) */
const AIUC1_CONTROLS: Record<string, string[]> = {
  data_privacy: [
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
  ],
  security: [
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
  ],
  safety: [
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
  ],
  reliability: [
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
  ],
  accountability: [
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
  ],
  society: [
    "f001_1_foundation_model_cyber_capabilities",
    "f001_2_cyber_use_detection",
    "f002_1_foundation_model_cbrn_capabilities",
    "f002_2_catastrophic_misuse_monitoring",
  ],
};

const AIUC1_CATEGORY_LABELS: Record<string, string> = {
  data_privacy: "A. Data & Privacy",
  security: "B. Security",
  safety: "C. Safety",
  reliability: "D. Reliability",
  accountability: "E. Accountability",
  society: "F. Society",
};

/** Add Rule inline picker */
function AddRulePanel({
  onAdd,
  onCancel,
}: {
  onAdd: (rule: GateRuleData) => void;
  onCancel: () => void;
}) {
  const [selectedType, setSelectedType] = useState("");
  const [threshold, setThreshold] = useState("");
  const [aiOnly, setAiOnly] = useState(false);
  const [category, setCategory] = useState("");
  const [control, setControl] = useState("");

  const meta = GATE_RULE_TYPES.find((r) => r.value === selectedType);

  const handleAdd = () => {
    if (!meta) return;
    const ruleId = `rule_${selectedType}`;
    const params: Record<string, unknown> = {};
    if (meta.hasParams) {
      if (category) params["category"] = category;
      if (control) params["control"] = control;
    }
    onAdd({
      rule_id: ruleId,
      rule_type: selectedType,
      description: meta.label,
      required: true,
      ai_only: meta.aiOnly || aiOnly,
      threshold: meta.hasThreshold && threshold !== "" ? Number(threshold) : null,
      parameters: meta.hasParams ? params : undefined,
    });
  };

  const groups = [...new Set(GATE_RULE_TYPES.map((r) => r.group))];

  return (
    <div className="mt-3 p-3 border border-clinical-cyan/30 rounded bg-vault-black/50 space-y-3">
      <div className="text-xs font-mono text-clinical-cyan font-semibold">Add Rule</div>
      <select
        className="input-vault text-xs w-full"
        value={selectedType}
        onChange={(e) => {
          setSelectedType(e.target.value);
          const m = GATE_RULE_TYPES.find((r) => r.value === e.target.value);
          if (m) setAiOnly(m.aiOnly);
        }}
      >
        <option value="">Select rule type…</option>
        {groups.map((g) => (
          <optgroup key={g} label={g}>
            {GATE_RULE_TYPES.filter((r) => r.group === g).map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </optgroup>
        ))}
      </select>

      {meta?.hasThreshold && (
        <div className="flex items-center gap-2">
          <label className="text-xs font-mono text-bone-muted w-24">Threshold</label>
          <input
            type="number"
            className="input-vault text-xs w-24"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </div>
      )}

      {meta?.hasParams && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Category</label>
            <select
              className="input-vault text-xs flex-1"
              value={category}
              onChange={(e) => { setCategory(e.target.value); setControl(""); }}
            >
              <option value="">Select category…</option>
              {Object.keys(AIUC1_CONTROLS).map((cat) => (
                <option key={cat} value={cat}>
                  {AIUC1_CATEGORY_LABELS[cat] ?? cat}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Control</label>
            <select
              className="input-vault text-xs flex-1"
              value={control}
              onChange={(e) => setControl(e.target.value)}
              disabled={!category}
            >
              <option value="">Select control…</option>
              {(AIUC1_CONTROLS[category] ?? []).map((k) => (
                <option key={k} value={k}>{fieldKeyToAiuc1Label(k)}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {meta && !meta.aiOnly && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={aiOnly}
            onChange={(e) => setAiOnly(e.target.checked)}
            className="accent-cold-teal"
          />
          <span className="text-xs font-mono text-bone-muted">AI only</span>
        </label>
      )}

      <div className="flex items-center gap-2 justify-end">
        <button className="btn-ghost text-xs" onClick={onCancel}>Cancel</button>
        <button
          className="btn-teal text-xs flex items-center gap-1"
          disabled={!selectedType || (meta?.hasParams ? !category || !control : false)}
          onClick={handleAdd}
        >
          <Plus size={12} /> Add Rule
        </button>
      </div>
    </div>
  );
}

function GateCard({
  gate,
  localState,
  onToggleRule,
  onThresholdChange,
  onSave,
  onToggleApproval,
  onDelete,
  onAddRule,
  onRemoveRule,
  isSaving,
}: {
  gate: GateData;
  localState: LocalGateState;
  onToggleRule: (ruleId: string) => void;
  onThresholdChange: (ruleId: string, val: number | null) => void;
  onSave: () => void;
  onToggleApproval: () => void;
  onDelete: () => void;
  onAddRule: (rule: GateRuleData) => void;
  onRemoveRule: (ruleId: string) => void;
  isSaving: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showAddRule, setShowAddRule] = useState(false);

  return (
    <VaultCard>
      {/* Header */}
      <div
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3">
          {expanded ? (
            <ChevronDown size={14} className="text-bone-muted" />
          ) : (
            <ChevronRight size={14} className="text-bone-muted" />
          )}
          <EnvBadge env={gate.source_environment} />
          <span className="text-bone-dim font-mono text-xs">&rarr;</span>
          <EnvBadge env={gate.target_environment} />
          {localState.dirty && (
            <span className="text-[10px] font-mono text-clinical-cyan bg-charcoal px-1.5 py-0.5 rounded">
              unsaved
            </span>
          )}
        </div>
        <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={onToggleApproval}
            className="flex items-center gap-2 text-xs font-mono"
          >
            {gate.approval_mode === "auto" ? (
              <>
                <ToggleRight size={18} className="text-cold-teal" />
                <span className="text-cold-teal">auto-approve</span>
              </>
            ) : (
              <>
                <ToggleLeft size={18} className="text-bone-muted" />
                <span className="text-bone-muted">manual</span>
              </>
            )}
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1 rounded hover:bg-dried-blood/20 text-bone-dim hover:text-dried-blood-bright transition-colors"
            title="Delete gate"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Delete confirmation */}
      {showDeleteConfirm && (
        <div className="mt-3 p-3 border border-dried-blood/40 rounded bg-vault-black/50 flex items-center gap-3">
          <AlertTriangle size={14} className="text-dried-blood-bright shrink-0" />
          <span className="text-xs font-mono text-bone flex-1">Delete this gate? This cannot be undone.</span>
          <button className="btn-ghost text-xs" onClick={() => setShowDeleteConfirm(false)}>Cancel</button>
          <button
            className="text-xs font-mono text-dried-blood-bright hover:underline"
            onClick={() => { setShowDeleteConfirm(false); onDelete(); }}
          >
            Delete
          </button>
        </div>
      )}

      {/* Expanded rule list */}
      {expanded && (
        <div className="mt-4 space-y-2">
          {localState.rules.length === 0 ? (
            <p className="text-bone-dim font-mono text-xs py-3 text-center">
              No rules — add rules below
            </p>
          ) : (
            localState.rules.map((rule) => (
              <div
                key={rule.rule_id}
                className="flex items-center gap-3 px-3 py-2.5 bg-vault-black/50 rounded border border-slate-border/30"
              >
                {/* Enabled checkbox */}
                <input
                  type="checkbox"
                  checked={rule._enabled}
                  onChange={() => onToggleRule(rule.rule_id)}
                  className="accent-cold-teal shrink-0"
                />
                {/* Rule details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-bone font-heading font-semibold">
                      {humanize(rule.rule_type)}
                    </span>
                    {rule.ai_only && (
                      <span className="text-[10px] font-mono text-clinical-cyan bg-charcoal px-1.5 py-0.5 rounded">
                        AI only
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-bone-muted font-mono mt-0.5 truncate">
                    {rule.description}
                  </p>
                </div>
                {/* Threshold input */}
                {rule.threshold !== undefined && rule.threshold !== null && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-bone-dim font-mono">
                      threshold
                    </span>
                    <input
                      type="number"
                      className="input-vault text-xs w-16 text-center"
                      value={rule._threshold ?? ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        onThresholdChange(
                          rule.rule_id,
                          v === "" ? null : Number(v)
                        );
                      }}
                    />
                  </div>
                )}
                {/* Remove rule */}
                <button
                  onClick={() => onRemoveRule(rule.rule_id)}
                  className="shrink-0 p-1 rounded hover:bg-dried-blood/20 text-bone-dim hover:text-dried-blood-bright transition-colors"
                  title="Remove rule"
                >
                  <X size={12} />
                </button>
              </div>
            ))
          )}

          {/* Add Rule panel */}
          {showAddRule ? (
            <AddRulePanel
              onAdd={(rule) => { onAddRule(rule); setShowAddRule(false); }}
              onCancel={() => setShowAddRule(false)}
            />
          ) : (
            <button
              className="w-full flex items-center justify-center gap-1.5 py-2 text-xs font-mono text-bone-muted hover:text-cold-teal border border-dashed border-slate-border/40 hover:border-cold-teal/40 rounded transition-colors"
              onClick={() => setShowAddRule(true)}
            >
              <Plus size={12} /> Add Rule
            </button>
          )}

          {/* Save button */}
          {localState.dirty && (
            <div className="flex items-center justify-end pt-2">
              <button
                className="btn-teal text-sm flex items-center gap-1.5"
                disabled={isSaving}
                onClick={onSave}
              >
                {isSaving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                Save Rules
              </button>
            </div>
          )}
        </div>
      )}
    </VaultCard>
  );
}

function GateRulesTab() {
  const { data: gates, isLoading } = useGates();
  const { data: pipeline } = useDefaultPipeline();
  const updateRulesMut = useUpdateGateRules();
  const updateModeMut = useUpdateGateApprovalMode();
  const createGateMut = useCreateGate();
  const deleteGateMut = useDeleteGate();

  // Local editable state keyed by gate_id
  const [localGates, setLocalGates] = useState<
    Record<string, LocalGateState>
  >({});

  // New Gate form state
  const [showNewGate, setShowNewGate] = useState(false);
  const [newGateSrc, setNewGateSrc] = useState("");
  const [newGateTgt, setNewGateTgt] = useState("");

  // Stage keys from the default pipeline for the "New Gate" env dropdowns
  const stageKeys = useMemo(() => {
    if (!pipeline?.stages) return [];
    return [...pipeline.stages].sort((a, b) => a.order - b.order);
  }, [pipeline]);

  // Initialise local state when gates load
  useEffect(() => {
    if (!gates) return;
    setLocalGates((prev) => {
      const next: Record<string, LocalGateState> = {};
      for (const g of gates) {
        const existing = prev[g.gate_id];
        if (existing && existing.dirty) {
          next[g.gate_id] = existing;
        } else {
          next[g.gate_id] = {
            rules: (g.rules ?? []).map((r) => ({
              ...r,
              _enabled: r.required,
              _threshold: r.threshold ?? null,
            })),
            dirty: false,
          };
        }
      }
      return next;
    });
  }, [gates]);

  const toggleRule = (gateId: string, ruleId: string) => {
    setLocalGates((prev) => {
      const gs = prev[gateId];
      if (!gs) return prev;
      return {
        ...prev,
        [gateId]: {
          ...gs,
          dirty: true,
          rules: gs.rules.map((r) =>
            r.rule_id === ruleId ? { ...r, _enabled: !r._enabled } : r
          ),
        },
      };
    });
  };

  const changeThreshold = (
    gateId: string,
    ruleId: string,
    val: number | null
  ) => {
    setLocalGates((prev) => {
      const gs = prev[gateId];
      if (!gs) return prev;
      return {
        ...prev,
        [gateId]: {
          ...gs,
          dirty: true,
          rules: gs.rules.map((r) =>
            r.rule_id === ruleId ? { ...r, _threshold: val } : r
          ),
        },
      };
    });
  };

  const addRule = (gateId: string, rule: GateRuleData) => {
    setLocalGates((prev) => {
      const gs = prev[gateId];
      if (!gs) return prev;
      // avoid duplicates
      const exists = gs.rules.some((r) => r.rule_id === rule.rule_id);
      const newRule = { ...rule, _enabled: true, _threshold: rule.threshold ?? null };
      return {
        ...prev,
        [gateId]: {
          dirty: true,
          rules: exists ? gs.rules : [...gs.rules, newRule],
        },
      };
    });
  };

  const removeRule = (gateId: string, ruleId: string) => {
    setLocalGates((prev) => {
      const gs = prev[gateId];
      if (!gs) return prev;
      return {
        ...prev,
        [gateId]: { dirty: true, rules: gs.rules.filter((r) => r.rule_id !== ruleId) },
      };
    });
  };

  const handleSave = (gateId: string) => {
    const gs = localGates[gateId];
    if (!gs) return;
    const enabledRules: GateRuleData[] = gs.rules
      .filter((r) => r._enabled)
      .map(({ _enabled, _threshold, ...rest }) => ({
        ...rest,
        required: true,
        threshold: _threshold,
      }));
    updateRulesMut.mutate(
      { gateId, rules: enabledRules },
      {
        onSuccess: () => {
          setLocalGates((prev) => {
            const existing = prev[gateId];
            if (!existing) return prev;
            return { ...prev, [gateId]: { ...existing, dirty: false } };
          });
        },
      }
    );
  };

  const handleToggleApproval = (gate: GateData) => {
    const newMode = gate.approval_mode === "auto" ? "manual" : "auto";
    updateModeMut.mutate({ gateId: gate.gate_id, approvalMode: newMode });
  };

  const handleDeleteGate = (gateId: string) => {
    deleteGateMut.mutate({ gateId });
  };

  const handleCreateGate = () => {
    if (!newGateSrc || !newGateTgt) return;
    createGateMut.mutate(
      { sourceEnvironment: newGateSrc, targetEnvironment: newGateTgt },
      {
        onSuccess: () => {
          setShowNewGate(false);
          setNewGateSrc("");
          setNewGateTgt("");
        },
      }
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-6 justify-center">
        <Loader2 size={16} className="animate-spin" /> Loading gate rules...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with New Gate button */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-bone-muted font-mono">
          {gates?.length ?? 0} gate{gates?.length !== 1 ? "s" : ""} configured
        </p>
        <button
          className="btn-ghost text-sm flex items-center gap-1.5"
          onClick={() => setShowNewGate((v) => !v)}
        >
          <Plus size={14} />
          New Gate
        </button>
      </div>

      {/* New Gate inline form */}
      {showNewGate && (
        <VaultCard className="border-clinical-cyan/30">
          <div className="text-xs font-mono text-clinical-cyan font-semibold mb-3">Create Gate</div>
          <div className="flex items-center gap-3 flex-wrap">
            <select
              className="input-vault text-xs flex-1 min-w-[120px]"
              value={newGateSrc}
              onChange={(e) => setNewGateSrc(e.target.value)}
            >
              <option value="">Source env…</option>
              {stageKeys.map((s) => (
                <option key={s.key} value={s.key}>{s.label} ({s.key})</option>
              ))}
            </select>
            <ArrowRight size={14} className="text-bone-dim shrink-0" />
            <select
              className="input-vault text-xs flex-1 min-w-[120px]"
              value={newGateTgt}
              onChange={(e) => setNewGateTgt(e.target.value)}
            >
              <option value="">Target env…</option>
              {stageKeys.map((s) => (
                <option key={s.key} value={s.key}>{s.label} ({s.key})</option>
              ))}
            </select>
            <div className="flex items-center gap-2 shrink-0">
              <button className="btn-ghost text-xs" onClick={() => setShowNewGate(false)}>Cancel</button>
              <button
                className="btn-teal text-xs flex items-center gap-1"
                disabled={!newGateSrc || !newGateTgt || newGateSrc === newGateTgt || createGateMut.isPending}
                onClick={handleCreateGate}
              >
                {createGateMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                Create Gate
              </button>
            </div>
          </div>
        </VaultCard>
      )}

      {(!gates || gates.length === 0) && !showNewGate && (
        <VaultCard className="text-center py-8">
          <ShieldCheck size={24} className="text-bone-dim mx-auto mb-2" />
          <p className="text-bone-dim font-mono text-sm">
            No promotion gates configured
          </p>
        </VaultCard>
      )}

      {gates?.map((gate) => (
        <GateCard
          key={gate.gate_id}
          gate={gate}
          localState={
            localGates[gate.gate_id] ?? { rules: [], dirty: false }
          }
          onToggleRule={(ruleId) => toggleRule(gate.gate_id, ruleId)}
          onThresholdChange={(ruleId, val) =>
            changeThreshold(gate.gate_id, ruleId, val)
          }
          onSave={() => handleSave(gate.gate_id)}
          onToggleApproval={() => handleToggleApproval(gate)}
          onDelete={() => handleDeleteGate(gate.gate_id)}
          onAddRule={(rule) => addRule(gate.gate_id, rule)}
          onRemoveRule={(ruleId) => removeRule(gate.gate_id, ruleId)}
          isSaving={updateRulesMut.isPending}
        />
      ))}
    </div>
  );
}

/* ================================================================== */
/*  TAB 3 -- Org Baseline                                             */
/* ================================================================== */

/** AIUC-1 standard domain keys — the 6 required categories */
const BASELINE_CATEGORIES = [
  "data_privacy",
  "security",
  "safety",
  "reliability",
  "accountability",
  "society",
] as const;

type BaselineCategory = (typeof BASELINE_CATEGORIES)[number];

/** Human label and description for each AIUC-1 domain */
const CATEGORY_META: Record<BaselineCategory, { label: string; description: string }> = {
  data_privacy: {
    label: "A. Data & Privacy",
    description: "Protect against data leakage, IP leakage, and training on user data without consent",
  },
  security: {
    label: "B. Security",
    description: "Protect against adversarial attacks, jailbreaks, prompt injections, and unauthorized tool calls",
  },
  safety: {
    label: "C. Safety",
    description: "Keep customers safe by mitigating harmful AI outputs and protecting brand reputation",
  },
  reliability: {
    label: "D. Reliability",
    description: "Prevent unreliable AI outputs through testing against hallucinations and unsafe tool calls",
  },
  accountability: {
    label: "E. Accountability",
    description: "Enforce governance through failure plans, vendor due diligence, and oversight mechanisms",
  },
  society: {
    label: "F. Society",
    description: "Prevent AI from enabling catastrophic societal harm through cyber exploitation and CBRN misuse",
  },
};

/** Fallback environments used when pipeline hasn't loaded */
const FALLBACK_ENVS = ["sandbox", "dev", "preprod", "prod"];

/**
 * Convert a snake_case field key like "b001_1_adversarial_testing_report"
 * to AIUC-1 label format: "B001.1: Adversarial testing report"
 */
function fieldKeyToAiuc1Label(fieldKey: string): string {
  const match = fieldKey.match(/^([a-f])(\d{3})_(\d+)_(.+)$/);
  if (!match) return humanize(fieldKey);
  const letter = match[1]!;
  const controlNum = match[2]!;
  const subNum = match[3]!;
  const rest = match[4]!;
  const id = `${letter.toUpperCase()}${controlNum}.${subNum}`;
  const name = rest.replace(/_/g, " ");
  return `${id}: ${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}

/** Extract just the AIUC-1 ID part, e.g. "b001_1_..." → "B001.1" */
function fieldKeyToAiuc1Id(fieldKey: string): string {
  const match = fieldKey.match(/^([a-f])(\d{3})_(\d+)/);
  if (!match) return fieldKey.toUpperCase();
  const letter = match[1]!;
  const controlNum = match[2]!;
  const subNum = match[3]!;
  return `${letter.toUpperCase()}${controlNum}.${subNum}`;
}

function BaselineTab() {
  const [projectId, setProjectId] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editedDefaults, setEditedDefaults] = useState<
    Record<string, Record<string, unknown>> | null
  >(null);
  const [editedRequirements, setEditedRequirements] =
    useState<Record<string, string[]> | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set()
  );
  const [reqExpanded, setReqExpanded] = useState(false);
  const [activeReqEnv, setActiveReqEnv] = useState<string>("prod");
  // Per-env, per-category expand state for requirements edit panel
  const [reqCatExpanded, setReqCatExpanded] = useState<Set<string>>(new Set());

  const { data: pipeline } = useDefaultPipeline();
  // Ordered stage keys from the pipeline, falling back to the static list
  const promotionEnvs = useMemo(() => {
    if (pipeline?.stages && pipeline.stages.length > 0) {
      return [...pipeline.stages]
        .sort((a, b) => a.order - b.order)
        .map((s) => s.key);
    }
    return FALLBACK_ENVS;
  }, [pipeline]);

  const { data: baseline, isLoading, isError } = useOrgBaseline(projectId);
  const saveMut = useSaveOrgBaseline();

  // Reset edit state when baseline or project changes
  useEffect(() => {
    setEditMode(false);
    setEditedDefaults(null);
    setEditedRequirements(null);
  }, [projectId, baseline]);

  const toggleSection = (cat: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const toggleReqCat = (key: string) => {
    setReqCatExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const enterEditMode = () => {
    if (!baseline) return;
    setEditedDefaults(
      JSON.parse(JSON.stringify(baseline.defaults)) as Record<
        string,
        Record<string, unknown>
      >
    );
    const emptyReqs: Record<string, string[]> = {};
    for (const key of promotionEnvs) emptyReqs[key] = [];
    setEditedRequirements(
      baseline.environment_requirements
        ? (JSON.parse(
            JSON.stringify(baseline.environment_requirements)
          ) as Record<string, string[]>)
        : emptyReqs
    );
    setEditMode(true);
  };

  const handleFieldChange = (
    category: string,
    field: string,
    value: boolean | null
  ) => {
    setEditedDefaults((prev) => {
      if (!prev) return prev;
      return { ...prev, [category]: { ...prev[category], [field]: value } };
    });
  };

  const handleToggleRequirement = (env: string, controlRef: string) => {
    setEditedRequirements((prev) => {
      if (!prev) return prev;
      const current = prev[env] ?? [];
      const next = current.includes(controlRef)
        ? current.filter((r) => r !== controlRef)
        : [...current, controlRef].sort();
      return { ...prev, [env]: next };
    });
  };

  const handleSave = () => {
    if (!baseline || !editedDefaults) return;
    const requirementsPayload =
      editedRequirements ?? baseline.environment_requirements;
    saveMut.mutate(
      {
        projectId,
        data: {
          schema_version: "1.1",
          kind: "PearlOrgBaseline",
          baseline_id: baseline.baseline_id,
          org_name: baseline.org_name,
          defaults: editedDefaults,
          ...(requirementsPayload
            ? { environment_requirements: requirementsPayload }
            : {}),
        },
      },
      {
        onSuccess: () => {
          setEditMode(false);
          setEditedDefaults(null);
          setEditedRequirements(null);
        },
      }
    );
  };

  const currentDefaults =
    editMode && editedDefaults ? editedDefaults : baseline?.defaults;
  const currentRequirements =
    editMode && editedRequirements
      ? editedRequirements
      : baseline?.environment_requirements;

  const categories = useMemo(() => {
    if (!currentDefaults) return [];
    return BASELINE_CATEGORIES.filter((c) => c in currentDefaults);
  }, [currentDefaults]);

  function renderValue(val: unknown) {
    if (val === true) return <Check size={14} className="text-cold-teal" />;
    if (val === false)
      return <X size={14} className="text-dried-blood-bright" />;
    return <Minus size={14} className="text-bone-dim" />;
  }

  function triStateNext(current: unknown): boolean | null {
    if (current === true) return false;
    if (current === false) return null;
    return true;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <ProjectSelector value={projectId} onChange={setProjectId} />
        {baseline && !editMode && (
          <button
            className="btn-ghost text-sm flex items-center gap-1.5"
            onClick={enterEditMode}
          >
            <Edit2 size={14} />
            Edit
          </button>
        )}
        {editMode && (
          <div className="flex items-center gap-2">
            <button
              className="btn-ghost text-sm"
              onClick={() => {
                setEditMode(false);
                setEditedDefaults(null);
                setEditedRequirements(null);
              }}
            >
              Cancel
            </button>
            <button
              className="btn-teal text-sm flex items-center gap-1.5"
              disabled={saveMut.isPending}
              onClick={handleSave}
            >
              {saveMut.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Save size={14} />
              )}
              Save Baseline
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {!projectId ? (
        <VaultCard className="text-center py-8">
          <p className="text-bone-dim font-mono text-sm">
            Select a project to view its org baseline
          </p>
        </VaultCard>
      ) : isLoading ? (
        <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-6 justify-center">
          <Loader2 size={16} className="animate-spin" /> Loading baseline...
        </div>
      ) : isError || !baseline ? (
        <VaultCard className="text-center py-8">
          <FileCode size={24} className="text-bone-dim mx-auto mb-2" />
          <p className="text-bone-dim font-mono text-sm">
            No baseline configured for this project
          </p>
        </VaultCard>
      ) : (
        <div className="space-y-3">
          {/* ---- AIUC-1 domain control cards ---- */}
          {categories.map((cat) => {
            const fields = currentDefaults?.[cat] ?? {};
            const isExpanded = expandedSections.has(cat);
            const meta = CATEGORY_META[cat];
            const trueCount = Object.values(fields).filter(
              (v) => v === true
            ).length;
            const totalCount = Object.keys(fields).length;
            return (
              <VaultCard key={cat}>
                <div
                  className="flex items-start gap-2 cursor-pointer select-none"
                  onClick={() => toggleSection(cat)}
                >
                  <div className="mt-0.5 shrink-0">
                    {isExpanded ? (
                      <ChevronDown size={14} className="text-bone-muted" />
                    ) : (
                      <ChevronRight size={14} className="text-bone-muted" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="vault-heading text-xs">{meta.label}</h3>
                    <p className="text-[10px] text-bone-muted font-mono mt-0.5 leading-relaxed">
                      {meta.description}
                    </p>
                  </div>
                  <div className="text-right shrink-0 ml-4">
                    <span className="text-[10px] text-cold-teal font-mono">
                      {trueCount}
                    </span>
                    <span className="text-[10px] text-bone-dim font-mono">
                      /{totalCount}
                    </span>
                    <div className="text-[9px] text-bone-dim font-mono">
                      enabled
                    </div>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-3 space-y-1">
                    {Object.entries(fields).map(([fieldKey, fieldVal]) => (
                      <div
                        key={fieldKey}
                        className="flex items-center justify-between px-3 py-2 bg-vault-black/50 rounded gap-3"
                      >
                        <span className="text-xs text-bone font-mono flex-1 min-w-0 truncate">
                          {fieldKeyToAiuc1Label(fieldKey)}
                        </span>
                        {editMode ? (
                          <button
                            className="p-1 rounded hover:bg-charcoal transition-colors shrink-0"
                            onClick={() =>
                              handleFieldChange(
                                cat,
                                fieldKey,
                                triStateNext(fieldVal)
                              )
                            }
                            title="Click to cycle: enabled → disabled → not assessed"
                          >
                            {renderValue(fieldVal)}
                          </button>
                        ) : (
                          <span className="shrink-0">
                            {renderValue(fieldVal)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </VaultCard>
            );
          })}

          {/* ---- Promotion Requirements ---- */}
          <VaultCard>
            <div
              className="flex items-center gap-2 cursor-pointer select-none"
              onClick={() => setReqExpanded((v) => !v)}
            >
              {reqExpanded ? (
                <ChevronDown size={14} className="text-bone-muted" />
              ) : (
                <ChevronRight size={14} className="text-bone-muted" />
              )}
              <div className="flex-1">
                <h3 className="vault-heading text-xs">Promotion Requirements</h3>
                <p className="text-[10px] text-bone-muted font-mono mt-0.5">
                  AIUC-1 sub-controls required to be enabled before promotion to
                  each environment
                </p>
              </div>
              <span className="text-[10px] text-bone-dim font-mono shrink-0">
                {promotionEnvs.map((e) => {
                  const count = currentRequirements?.[e]?.length ?? 0;
                  return count > 0 ? (
                    <span key={e} className="ml-2">
                      <span className="text-clinical-cyan">{e}</span>:{" "}
                      {count}
                    </span>
                  ) : null;
                })}
              </span>
            </div>

            {reqExpanded && (
              <div className="mt-4 space-y-3">
                {/* Env selector tabs */}
                <div className="flex gap-0 border-b border-slate-border/50 flex-wrap">
                  {promotionEnvs.map((env) => {
                    const count = currentRequirements?.[env]?.length ?? 0;
                    return (
                      <button
                        key={env}
                        onClick={() => setActiveReqEnv(env)}
                        className={`px-4 py-2 text-xs font-mono border-b-2 -mb-px transition-colors ${
                          activeReqEnv === env
                            ? "border-cold-teal text-cold-teal"
                            : "border-transparent text-bone-muted hover:text-bone"
                        }`}
                      >
                        {env}
                        {count > 0 && (
                          <span className="ml-1.5 text-[9px] bg-charcoal px-1 py-0.5 rounded">
                            {count}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Requirements for active env */}
                {editMode ? (
                  /* Edit mode: full checkbox tree grouped by category */
                  <div className="space-y-2">
                    {categories.map((cat) => {
                      const catKey = `${activeReqEnv}-${cat}`;
                      const isCatOpen = reqCatExpanded.has(catKey);
                      const catFields = currentDefaults?.[cat] ?? {};
                      const catReqCount = Object.keys(catFields).filter((fk) =>
                        editedRequirements?.[activeReqEnv]?.includes(
                          `${cat}.${fk}`
                        )
                      ).length;
                      return (
                        <div
                          key={cat}
                          className="border border-slate-border/30 rounded"
                        >
                          <button
                            className="w-full flex items-center gap-2 px-3 py-2 hover:bg-vault-black/30 transition-colors"
                            onClick={() => toggleReqCat(catKey)}
                          >
                            {isCatOpen ? (
                              <ChevronDown
                                size={12}
                                className="text-bone-dim shrink-0"
                              />
                            ) : (
                              <ChevronRight
                                size={12}
                                className="text-bone-dim shrink-0"
                              />
                            )}
                            <span className="text-xs font-mono text-clinical-cyan font-semibold">
                              {CATEGORY_META[cat].label}
                            </span>
                            {catReqCount > 0 && (
                              <span className="ml-auto text-[9px] text-cold-teal font-mono bg-charcoal px-1.5 py-0.5 rounded">
                                {catReqCount} required
                              </span>
                            )}
                          </button>
                          {isCatOpen && (
                            <div className="border-t border-slate-border/20 divide-y divide-slate-border/10">
                              {Object.keys(catFields).map((fieldKey) => {
                                const controlRef = `${cat}.${fieldKey}`;
                                const isReq =
                                  (editedRequirements?.[activeReqEnv] ?? []).includes(controlRef);
                                return (
                                  <label
                                    key={fieldKey}
                                    className="flex items-center gap-3 px-4 py-2 hover:bg-vault-black/30 cursor-pointer"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isReq}
                                      onChange={() =>
                                        handleToggleRequirement(activeReqEnv, controlRef)
                                      }
                                      className="accent-cold-teal shrink-0"
                                    />
                                    <span className="text-xs font-mono text-bone">
                                      {fieldKeyToAiuc1Label(fieldKey)}
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  /* View mode: compact chips */
                  <div className="space-y-3">
                    {(() => {
                      const reqs = (currentRequirements as Record<string, string[]> | null)?.[activeReqEnv] ?? [];
                      if (reqs.length === 0) {
                        return (
                          <p className="text-xs text-bone-dim font-mono py-4 text-center">
                            No requirements configured for {activeReqEnv}
                          </p>
                        );
                      }
                      // Group by category
                      const grouped: Record<string, string[]> = {};
                      for (const ref of reqs) {
                        const dot = ref.indexOf(".");
                        if (dot === -1) continue;
                        const c = ref.slice(0, dot);
                        const fk = ref.slice(dot + 1);
                        if (!grouped[c]) grouped[c] = [];
                        grouped[c].push(fk);
                      }
                      return Object.entries(grouped).map(([cat, fks]) => (
                        <div key={cat}>
                          <div className="text-[10px] font-mono text-clinical-cyan font-semibold uppercase tracking-wider mb-1.5">
                            {CATEGORY_META[cat as BaselineCategory]?.label ??
                              cat}
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {fks.map((fk) => (
                              <span
                                key={fk}
                                className="text-[10px] font-mono bg-charcoal border border-slate-border/40 text-bone-muted px-2 py-0.5 rounded"
                                title={fieldKeyToAiuc1Label(fk)}
                              >
                                {fieldKeyToAiuc1Id(fk)}
                              </span>
                            ))}
                          </div>
                        </div>
                      ));
                    })()}
                  </div>
                )}
              </div>
            )}
          </VaultCard>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  TAB 4 -- Notifications                                            */
/* ================================================================== */

function NotificationsTab() {
  const [projectId, setProjectId] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");

  const { data: integrations } = useIntegrations(projectId);
  const createMut = useCreateIntegration();

  // Find existing slack sink
  const slackIntegration = useMemo(
    () =>
      integrations?.find(
        (i) => i.adapter_type === "slack" && i.integration_type === "sink"
      ) ?? null,
    [integrations]
  );

  const hasSlack = slackIntegration !== null;

  // Pre-fill URL from existing slack integration
  useEffect(() => {
    if (slackIntegration) {
      setWebhookUrl(slackIntegration.base_url);
    } else {
      setWebhookUrl("");
    }
  }, [slackIntegration]);

  const handleSaveSlack = () => {
    if (!projectId || !webhookUrl) return;
    createMut.mutate({
      projectId,
      data: {
        name: "Slack Notifications",
        adapter_type: "slack",
        integration_type: "sink",
        category: "notification",
        base_url: webhookUrl,
      },
    });
  };

  return (
    <div className="space-y-4">
      {/* Project selector */}
      <div className="flex items-center">
        <ProjectSelector value={projectId} onChange={setProjectId} />
      </div>

      {/* Slack Webhook */}
      <VaultCard>
        <h2 className="vault-heading text-xs mb-3">Slack Webhook</h2>
        <div className="flex gap-2">
          <input
            className="input-vault flex-1 text-sm"
            placeholder="https://hooks.slack.com/services/..."
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
          />
          <button
            className="btn-teal text-sm flex items-center gap-1.5"
            onClick={handleSaveSlack}
            disabled={createMut.isPending || !webhookUrl || !projectId}
          >
            {createMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Save
          </button>
        </div>
        {hasSlack && (
          <p className="text-xs text-cold-teal font-mono mt-2">
            Slack integration active
          </p>
        )}
        {!hasSlack && projectId && (
          <p className="text-xs text-bone-dim font-mono mt-2">
            No Slack integration configured for this project
          </p>
        )}
      </VaultCard>

      {/* Event Routing */}
      <VaultCard>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="vault-heading text-xs">Event Routing</h2>
          <div className="group relative ml-auto">
            <Info size={14} className="text-bone-dim cursor-help" />
            <div className="absolute right-0 top-6 w-64 bg-charcoal border border-slate-border rounded p-2 text-xs text-bone-muted font-mono opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-10">
              Events route to all enabled notification sinks
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {EVENT_TYPES.map((event) => (
            <div
              key={event}
              className="flex items-center justify-between px-3 py-2 bg-vault-black/50 rounded"
            >
              <MonoText className="text-xs">{event}</MonoText>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-cold-teal">
                  dashboard
                </span>
                <span
                  className={`text-[10px] font-mono ${
                    hasSlack ? "text-cold-teal" : "text-bone-dim"
                  }`}
                >
                  slack
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-bone-dim font-mono mt-3">
          Events route to all enabled notification sinks
        </p>
      </VaultCard>
    </div>
  );
}

/* ================================================================== */
/*  TAB 5 — Environments                                              */
/* ================================================================== */

function EnvironmentsTab() {
  const { data: pipeline, isLoading } = useDefaultPipeline();
  const updatePipelineMut = useUpdatePipeline();

  // Local editable stages (sorted by order)
  const [localStages, setLocalStages] = useState<PipelineStage[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [removeConfirmIdx, setRemoveConfirmIdx] = useState<number | null>(null);

  // Initialise when pipeline loads
  useEffect(() => {
    if (!pipeline) return;
    setLocalStages(
      [...pipeline.stages].sort((a, b) => a.order - b.order)
    );
    setIsDirty(false);
  }, [pipeline]);

  const moveStage = (idx: number, dir: -1 | 1) => {
    setLocalStages((prev) => {
      if (idx + dir < 0 || idx + dir >= prev.length) return prev;
      const next = [...prev];
      // Swap order values
      const tmp = next[idx]!.order;
      next[idx] = { ...next[idx]!, order: next[idx + dir]!.order };
      next[idx + dir] = { ...next[idx + dir]!, order: tmp };
      return [...next].sort((a, b) => a.order - b.order);
    });
    setIsDirty(true);
  };

  const removeStage = (idx: number) => {
    setLocalStages((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      // Re-assign sequential orders
      return next.map((s, i) => ({ ...s, order: i }));
    });
    setRemoveConfirmIdx(null);
    setIsDirty(true);
  };

  const startEdit = (idx: number) => {
    const s = localStages[idx]!;
    setEditLabel(s.label);
    setEditDesc(s.description ?? "");
    setEditingIdx(idx);
  };

  const saveEdit = (idx: number) => {
    setLocalStages((prev) =>
      prev.map((s, i) =>
        i === idx ? { ...s, label: editLabel, description: editDesc || undefined } : s
      )
    );
    setEditingIdx(null);
    setIsDirty(true);
  };

  const addStage = () => {
    const key = newKey.trim().toLowerCase();
    if (!key || !newLabel.trim()) return;
    setLocalStages((prev) => [
      ...prev,
      { key, label: newLabel.trim(), description: newDesc.trim() || undefined, order: prev.length },
    ]);
    setNewKey("");
    setNewLabel("");
    setNewDesc("");
    setShowAddForm(false);
    setIsDirty(true);
  };

  const handleSave = () => {
    if (!pipeline) return;
    updatePipelineMut.mutate(
      { pipelineId: pipeline.pipeline_id, data: { stages: localStages } },
      { onSuccess: () => setIsDirty(false) }
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-6 justify-center">
        <Loader2 size={16} className="animate-spin" /> Loading pipeline…
      </div>
    );
  }

  if (!pipeline) {
    return (
      <VaultCard className="text-center py-8">
        <Layers size={24} className="text-bone-dim mx-auto mb-2" />
        <p className="text-bone-dim font-mono text-sm">No default pipeline found</p>
      </VaultCard>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="vault-heading text-sm mb-1">Promotion Pipeline</h2>
          <p className="text-xs text-bone-muted font-mono">
            <span className="text-cold-teal">{pipeline.name}</span>
            {pipeline.description && (
              <span className="ml-2 text-bone-dim">— {pipeline.description}</span>
            )}
          </p>
        </div>
        {isDirty && (
          <button
            className="btn-teal text-sm flex items-center gap-1.5"
            disabled={updatePipelineMut.isPending}
            onClick={handleSave}
          >
            {updatePipelineMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Save Pipeline
          </button>
        )}
      </div>

      {/* Visual chain */}
      <VaultCard>
        <div className="flex items-center justify-center gap-2 py-4 flex-wrap">
          {localStages.map((stage, i) => (
            <div key={stage.key} className="flex items-center gap-2">
              <div className="flex flex-col items-center gap-1">
                <EnvBadge env={stage.key} />
                <span className="text-[10px] text-bone-dim font-mono">{stage.label}</span>
              </div>
              {i < localStages.length - 1 && (
                <ArrowRight size={13} className="text-bone-dim" />
              )}
            </div>
          ))}
        </div>
      </VaultCard>

      {/* Stage cards */}
      <div className="space-y-2">
        {localStages.map((stage, idx) => (
          <VaultCard key={stage.key}>
            {editingIdx === idx ? (
              /* Edit mode for this stage */
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <EnvBadge env={stage.key} />
                  <span className="text-xs font-mono text-bone-dim">{stage.key}</span>
                  <span className="text-[10px] text-bone-dim font-mono ml-auto">(key is immutable)</span>
                </div>
                <input
                  className="input-vault text-sm w-full"
                  placeholder="Label"
                  value={editLabel}
                  onChange={(e) => setEditLabel(e.target.value)}
                />
                <input
                  className="input-vault text-xs w-full"
                  placeholder="Description (optional)"
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                />
                <div className="flex items-center gap-2 justify-end">
                  <button className="btn-ghost text-xs" onClick={() => setEditingIdx(null)}>Cancel</button>
                  <button className="btn-teal text-xs" onClick={() => saveEdit(idx)}>Save</button>
                </div>
              </div>
            ) : (
              /* View mode for this stage */
              <div className="flex items-start gap-3">
                <div className="flex items-center justify-center w-7 h-7 rounded-full bg-wet-stone text-bone-muted text-xs font-mono font-bold shrink-0">
                  {idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <EnvBadge env={stage.key} />
                    <span className="text-sm font-heading font-semibold text-bone">{stage.label}</span>
                    <span className="text-[10px] text-bone-dim font-mono">({stage.key})</span>
                  </div>
                  {stage.description && (
                    <p className="text-xs text-bone-muted font-mono">{stage.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => moveStage(idx, -1)}
                    disabled={idx === 0}
                    className="p-1 rounded hover:bg-charcoal disabled:opacity-30 transition-colors"
                    title="Move up"
                  >
                    <ChevronUp size={13} className="text-bone-muted" />
                  </button>
                  <button
                    onClick={() => moveStage(idx, 1)}
                    disabled={idx === localStages.length - 1}
                    className="p-1 rounded hover:bg-charcoal disabled:opacity-30 transition-colors"
                    title="Move down"
                  >
                    <ChevronDown size={13} className="text-bone-muted" />
                  </button>
                  <button
                    onClick={() => startEdit(idx)}
                    className="p-1 rounded hover:bg-charcoal transition-colors"
                    title="Edit stage"
                  >
                    <Edit2 size={13} className="text-bone-muted" />
                  </button>
                  {removeConfirmIdx === idx ? (
                    <div className="flex items-center gap-1 ml-1">
                      <span className="text-[10px] font-mono text-dried-blood-bright">Remove?</span>
                      <button
                        onClick={() => removeStage(idx)}
                        disabled={localStages.length <= 1}
                        className="text-[10px] font-mono text-dried-blood-bright hover:underline disabled:opacity-40"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => setRemoveConfirmIdx(null)}
                        className="text-[10px] font-mono text-bone-muted hover:underline"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setRemoveConfirmIdx(idx)}
                      disabled={localStages.length <= 1}
                      className="p-1 rounded hover:bg-dried-blood/20 disabled:opacity-30 transition-colors"
                      title="Remove stage"
                    >
                      <X size={13} className="text-bone-dim hover:text-dried-blood-bright" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </VaultCard>
        ))}
      </div>

      {/* Add Stage */}
      {showAddForm ? (
        <VaultCard className="border-clinical-cyan/30">
          <div className="text-xs font-mono text-clinical-cyan font-semibold mb-3">Add Stage</div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <label className="text-xs font-mono text-bone-muted w-20 shrink-0">Key</label>
              <input
                className="input-vault text-xs flex-1"
                placeholder="e.g. qa (lowercase, no spaces)"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-mono text-bone-muted w-20 shrink-0">Label</label>
              <input
                className="input-vault text-xs flex-1"
                placeholder="e.g. QA"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-mono text-bone-muted w-20 shrink-0">Description</label>
              <input
                className="input-vault text-xs flex-1"
                placeholder="Optional description"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 justify-end pt-1">
              <button className="btn-ghost text-xs" onClick={() => { setShowAddForm(false); setNewKey(""); setNewLabel(""); setNewDesc(""); }}>
                Cancel
              </button>
              <button
                className="btn-teal text-xs flex items-center gap-1"
                disabled={!newKey || !newLabel}
                onClick={addStage}
              >
                <Plus size={12} /> Add Stage
              </button>
            </div>
          </div>
        </VaultCard>
      ) : (
        <button
          className="w-full flex items-center justify-center gap-1.5 py-2.5 text-xs font-mono text-bone-muted hover:text-cold-teal border border-dashed border-slate-border/40 hover:border-cold-teal/40 rounded transition-colors"
          onClick={() => setShowAddForm(true)}
        >
          <Plus size={13} /> Add Stage
        </button>
      )}

      {isDirty && (
        <div className="flex items-center justify-end">
          <button
            className="btn-teal text-sm flex items-center gap-1.5"
            disabled={updatePipelineMut.isPending}
            onClick={handleSave}
          >
            {updatePipelineMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Save Pipeline
          </button>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Main Settings Page                                                */
/* ================================================================== */

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("integrations");

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Configuration</h1>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-slate-border">
        {TABS.map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-heading font-semibold uppercase tracking-wider transition-all border-b-2 -mb-px ${
              activeTab === key
                ? "border-cold-teal text-cold-teal"
                : "border-transparent text-bone-muted hover:text-bone"
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "integrations" && <IntegrationsTab />}
      {activeTab === "gates" && <GateRulesTab />}
      {activeTab === "baseline" && <BaselineTab />}
      {activeTab === "notifications" && <NotificationsTab />}
      {activeTab === "environments" && <EnvironmentsTab />}
    </div>
  );
}
