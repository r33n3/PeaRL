import { useState, useEffect, useMemo } from "react";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { MonoText } from "@/components/shared/MonoText";
import { FRAMEWORK_CONTROLS } from "@/lib/frameworkControls";
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
  useOrgIntegrations,
  useCreateOrgIntegration,
  useUpdateOrgIntegration,
  useDeleteOrgIntegration,
  useTestOrgIntegration,
  useEventRouting,
  useSaveEventRouting,
} from "@/api/integrations";
import { useDefaultPipeline, useUpdatePipeline } from "@/api/pipelines";
import type { PipelineStage } from "@/api/pipelines";
import { useProjects } from "@/api/dashboard";
import { AdminBusinessUnitsPage } from "./AdminBusinessUnitsPage";
import { AdminProjectsPage } from "./AdminProjectsPage";
import type { IntegrationEndpoint } from "@/lib/types";
import {
  Plug,
  ShieldCheck,
  Bell,
  RefreshCw,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Plus,
  ChevronDown,
  ChevronRight,
  X,
  Save,
  Edit2,
  Info,
  Loader2,
  Layers,
  ArrowRight,
  ChevronUp,
  AlertTriangle,
  Building2,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Tab = "gates" | "environments" | "business_units" | "integrations" | "project_data";

const TABS: { key: Tab; icon: typeof Plug; label: string }[] = [
  { key: "gates", icon: ShieldCheck, label: "Gate Rules" },
  { key: "environments", icon: Layers, label: "Environments" },
  { key: "business_units", icon: Building2, label: "Business Units" },
  { key: "integrations", icon: Plug, label: "Integrations" },
  { key: "project_data", icon: Trash2, label: "Project Data" },
];

/* ------------------------------------------------------------------ */
/*  Integration Catalogue                                              */
/* ------------------------------------------------------------------ */

interface CatalogueEntry {
  adapter_type: string;
  category: string;
  label: string;
  description: string;
}

const INTEGRATION_CATALOGUE: CatalogueEntry[] = [
  { adapter_type: "snyk",        category: "sca",           label: "Snyk",        description: "SCA / vulnerability scanning" },
  { adapter_type: "semgrep",     category: "sast",          label: "Semgrep",     description: "SAST / code analysis" },
  { adapter_type: "trivy",       category: "container_scan",label: "Trivy",       description: "Container & IaC scanning" },
  { adapter_type: "sonarqube",   category: "sast",          label: "SonarQube",   description: "Code quality & SAST" },
  { adapter_type: "github",      category: "git_platform",  label: "GitHub",      description: "Source code, PRs, Actions" },
  { adapter_type: "gitlab",      category: "git_platform",  label: "GitLab",      description: "Source code, MRs, CI/CD" },
  { adapter_type: "azure_devops",category: "ci_cd",         label: "Azure DevOps",description: "Repos, pipelines, work items" },
  { adapter_type: "jira",        category: "ticketing",     label: "Jira",        description: "Ticket & project management" },
  { adapter_type: "linear",      category: "ticketing",     label: "Linear",      description: "Issue tracking" },
  { adapter_type: "servicenow",  category: "ticketing",     label: "ServiceNow",  description: "Enterprise ITSM" },
  { adapter_type: "slack",       category: "notification",  label: "Slack",       description: "Team alerts & notifications" },
  { adapter_type: "teams",       category: "notification",  label: "Teams",       description: "Enterprise notifications" },
  { adapter_type: "webhook",     category: "notification",  label: "Webhook",     description: "Custom HTTP endpoint" },
  { adapter_type: "email",       category: "notification",  label: "Email",       description: "SMTP / email alerts" },
  { adapter_type: "pagerduty",   category: "notification",  label: "PagerDuty",   description: "Incident alerting" },
  { adapter_type: "mass",        category: "dast",          label: "MASS 2.0",    description: "AI deployment security scanner" },
];

const CATEGORY_ORDER = ["dast", "sast", "sca", "container_scan", "git_platform", "ci_cd", "ticketing", "notification"] as const;

const CATEGORY_LABELS: Record<string, string> = {
  dast:           "AI / Dynamic Scanners",
  sast:           "SAST / Code Quality",
  sca:            "SCA / Dependencies",
  container_scan: "Container & IaC Scanning",
  git_platform:   "Source Control",
  ci_cd:          "CI/CD",
  ticketing:      "Issue Tracking",
  notification:   "Notification Channels",
};

type ConfigFormState = Record<string, string>;

const TOKEN_ENV_PLACEHOLDERS: Record<string, string> = {
  sonarqube:   "SONARQUBE_TOKEN",
  snyk:        "SNYK_TOKEN",
  semgrep:     "SEMGREP_APP_TOKEN",
  trivy:       "TRIVY_TOKEN",
  github:      "GITHUB_TOKEN",
  gitlab:      "GITLAB_TOKEN",
  jira:        "JIRA_API_TOKEN",
  linear:      "LINEAR_API_KEY",
  servicenow:  "SERVICENOW_TOKEN",
  azure_devops:"AZURE_DEVOPS_TOKEN",
  mass:        "PEARL_MASS_API_KEY",
};

function getAdapterFields(adapter_type: string): { key: string; label: string; placeholder: string; hint?: string; type?: string; span?: "full" }[] {
  const webhookAdapters = ["slack", "teams", "webhook", "pagerduty"];
  const tokenAdapters = ["github", "gitlab", "snyk", "semgrep", "trivy", "sonarqube", "mass"];
  const ticketAdapters = ["jira", "linear", "servicenow", "azure_devops"];
  const envPlaceholder = TOKEN_ENV_PLACEHOLDERS[adapter_type] ?? "MY_TOKEN";
  const baseUrlPlaceholder = adapter_type === "sonarqube"
    ? "http://localhost:9000"
    : adapter_type === "mass"
    ? "http://host.docker.internal:80"
    : "https://api.example.com";
  if (webhookAdapters.includes(adapter_type)) {
    return [{ key: "webhook_url", label: "Webhook URL", placeholder: "https://...", span: "full" }];
  }
  if (tokenAdapters.includes(adapter_type)) {
    return [
      { key: "base_url",         label: "Base URL",              placeholder: baseUrlPlaceholder },
      { key: "raw_token",        label: "API Token",             placeholder: "Paste token — stored in DB (local/dev)", type: "password",
        hint: "No restart needed. For production use Token Env Var instead." },
      { key: "bearer_token_env", label: "Token Env Var (prod)",  placeholder: envPlaceholder,
        hint: `Server env var name — takes precedence over API Token if both are set. e.g. export ${envPlaceholder}=<token>` },
    ];
  }
  if (ticketAdapters.includes(adapter_type)) {
    return [
      { key: "base_url",         label: "Base URL",              placeholder: "https://yourorg.atlassian.net" },
      { key: "raw_token",        label: "API Token",             placeholder: "Paste token — stored in DB (local/dev)", type: "password",
        hint: "No restart needed. For production use Token Env Var instead." },
      { key: "bearer_token_env", label: "Token Env Var (prod)",  placeholder: envPlaceholder,
        hint: `Server env var name — takes precedence if set. e.g. export ${envPlaceholder}=<token>` },
      { key: "project_key",      label: "Project Key",           placeholder: "PROJ" },
    ];
  }
  if (adapter_type === "email") {
    return [
      { key: "smtp_host",     label: "SMTP Host",     placeholder: "smtp.example.com" },
      { key: "smtp_port",     label: "SMTP Port",     placeholder: "587" },
      { key: "from_address",  label: "From Address",  placeholder: "alerts@example.com" },
      { key: "to_addresses",  label: "To Addresses",  placeholder: "team@example.com" },
    ];
  }
  return [
    { key: "base_url",         label: "Base URL",      placeholder: "https://..." },
    { key: "raw_token",        label: "API Token",     placeholder: "token...", type: "password" },
    { key: "bearer_token_env", label: "Token Env Var", placeholder: envPlaceholder },
  ];
}

function buildAuthConfig(adapter_type: string, form: ConfigFormState): Record<string, string> {
  const config: Record<string, string> = {};
  const fields = getAdapterFields(adapter_type);
  fields.forEach(f => {
    if (f.key !== "base_url" && form[f.key] !== undefined && form[f.key] !== "") {
      config[f.key] = form[f.key] as string;
    }
  });
  if (form["bearer_token_env"] || form["raw_token"]) {
    config["auth_type"] = "bearer";
  }
  return config;
}

function buildBaseUrl(_adapter_type: string, form: ConfigFormState): string {
  return form["base_url"] ?? form["webhook_url"] ?? form["smtp_host"] ?? "";
}

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
/*  TAB 1 -- Integrations (categorized, org-level)                    */
/* ================================================================== */

function IntegrationsTab() {
  const { data: integrations, isLoading } = useOrgIntegrations();
  const createMut = useCreateOrgIntegration();
  const updateMut = useUpdateOrgIntegration();
  const deleteMut = useDeleteOrgIntegration();
  const testMut = useTestOrgIntegration();
  const { data: routingData, isLoading: routingLoading } = useEventRouting();
  const saveRoutingMut = useSaveEventRouting();
  const [routing, setRouting] = useState<Record<string, string[]>>({});
  const [isRoutingDirty, setIsRoutingDirty] = useState(false);

  useEffect(() => {
    if (routingData?.routing) {
      setRouting(routingData.routing);
      setIsRoutingDirty(false);
    }
  }, [routingData]);

  const toggleRoute = (event: string, adapter: string) => {
    setRouting(prev => {
      const current = new Set(prev[event] ?? []);
      if (current.has(adapter)) current.delete(adapter); else current.add(adapter);
      return { ...prev, [event]: Array.from(current) };
    });
    setIsRoutingDirty(true);
  };

  const [addingAdapter, setAddingAdapter] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [configForm, setConfigForm] = useState<ConfigFormState>({});
  const [addPickerCategory, setAddPickerCategory] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message?: string }>>({});

  const configuredByType = useMemo(() => {
    const map: Record<string, IntegrationEndpoint> = {};
    (integrations ?? []).filter(i => i.enabled).forEach(i => { map[i.adapter_type] = i; });
    return map;
  }, [integrations]);

  const handleStartAdd = (adapter_type: string) => {
    setAddingAdapter(adapter_type);
    setEditingId(null);
    setConfigForm({});
    setAddPickerCategory(null);
  };

  const handleStartEdit = (ep: IntegrationEndpoint) => {
    setEditingId(ep.endpoint_id);
    setAddingAdapter(null);
    const form: ConfigFormState = {};
    if (ep.auth_config) {
      Object.entries(ep.auth_config).forEach(([k, v]) => {
        if (typeof v === "string") form[k] = v;
      });
    }
    if (ep.base_url) form["base_url"] = ep.base_url;
    setConfigForm(form);
  };

  const handleCancelForm = () => {
    setAddingAdapter(null);
    setEditingId(null);
    setConfigForm({});
  };

  const handleSaveNew = (entry: CatalogueEntry) => {
    const integrationType = entry.category === "notification_channels" ? "sink" : "source";
    createMut.mutate({
      name: entry.label,
      adapter_type: entry.adapter_type,
      category: entry.category,
      integration_type: integrationType,
      base_url: buildBaseUrl(entry.adapter_type, configForm),
      auth_config: buildAuthConfig(entry.adapter_type, configForm),
    }, { onSuccess: handleCancelForm });
  };

  const handleSaveEdit = (ep: IntegrationEndpoint) => {
    updateMut.mutate({
      endpointId: ep.endpoint_id,
      data: {
        base_url: buildBaseUrl(ep.adapter_type, configForm),
        auth_config: buildAuthConfig(ep.adapter_type, configForm),
      },
    }, { onSuccess: handleCancelForm });
  };

  const handleDelete = (ep: IntegrationEndpoint) => {
    if (!window.confirm(`Remove ${ep.name} integration?`)) return;
    deleteMut.mutate({ endpointId: ep.endpoint_id });
  };

  const handleTest = (ep: IntegrationEndpoint) => {
    testMut.mutate({ endpointId: ep.endpoint_id }, {
      onSuccess: (result) => {
        setTestResults(prev => ({ ...prev, [ep.endpoint_id]: result as { success: boolean; message?: string } }));
        setTimeout(() => setTestResults(prev => { const n = { ...prev }; delete n[ep.endpoint_id]; return n; }), 4000);
      },
      onError: () => {
        setTestResults(prev => ({ ...prev, [ep.endpoint_id]: { success: false, message: "Connection failed" } }));
        setTimeout(() => setTestResults(prev => { const n = { ...prev }; delete n[ep.endpoint_id]; return n; }), 4000);
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-8 justify-center">
        <Loader2 size={16} className="animate-spin" /> Loading integrations...
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {CATEGORY_ORDER.map(category => {
        const catalogueEntries = INTEGRATION_CATALOGUE.filter(e => e.category === category);
        const configuredEntries = catalogueEntries.filter(e => !!configuredByType[e.adapter_type]);
        const unconfiguredEntries = catalogueEntries.filter(e => !configuredByType[e.adapter_type]);
        const isPickerOpen = addPickerCategory === category;
        const isAddingInCategory = addingAdapter && INTEGRATION_CATALOGUE.find(e => e.adapter_type === addingAdapter)?.category === category;

        return (
          <div key={category}>
            {/* Category header */}
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-heading font-semibold uppercase tracking-wider text-bone">
                {CATEGORY_LABELS[category]}
              </h3>
              {unconfiguredEntries.length > 0 && (
                <button
                  className="btn-ghost text-xs flex items-center gap-1"
                  onClick={() => setAddPickerCategory(isPickerOpen ? null : category)}
                >
                  <Plus size={12} /> Add
                </button>
              )}
            </div>

            {/* Add picker */}
            {isPickerOpen && (
              <VaultCard className="mb-3 space-y-2">
                <p className="text-xs font-mono text-bone-muted mb-2">Select an integration to configure:</p>
                <div className="grid grid-cols-2 gap-2">
                  {unconfiguredEntries.map(entry => (
                    <button
                      key={entry.adapter_type}
                      className="text-left px-3 py-2 rounded bg-vault-black/50 hover:bg-charcoal border border-slate-border/30 hover:border-cold-teal/40 transition-colors"
                      onClick={() => handleStartAdd(entry.adapter_type)}
                    >
                      <div className="text-sm font-semibold text-bone">{entry.label}</div>
                      <div className="text-xs text-bone-dim font-mono">{entry.description}</div>
                    </button>
                  ))}
                </div>
                <button className="btn-ghost text-xs" onClick={() => setAddPickerCategory(null)}>Cancel</button>
              </VaultCard>
            )}

            {/* Inline add form */}
            {isAddingInCategory && (() => {
              const entry = INTEGRATION_CATALOGUE.find(e => e.adapter_type === addingAdapter)!;
              const fields = getAdapterFields(addingAdapter!);
              return (
                <VaultCard className="mb-3 border-cold-teal/30 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-heading font-semibold text-bone">{entry.label}</span>
                    <span className="text-xs text-bone-dim font-mono">{entry.description}</span>
                  </div>
                  <div className="grid gap-2 grid-cols-2">
                    {fields.map(f => (
                      <div key={f.key} className={f.span === "full" || fields.length === 1 ? "col-span-full" : ""}>
                        <label className="text-[10px] font-mono text-bone-muted block mb-1">{f.label}</label>
                        <input
                          className="input-vault text-sm w-full"
                          type={f.type ?? "text"}
                          placeholder={f.placeholder}
                          value={configForm[f.key] ?? ""}
                          onChange={e => setConfigForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                        />
                        {f.hint && <p className="text-[9px] text-bone-dim font-mono mt-0.5 leading-tight">{f.hint}</p>}
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      className="btn-teal text-sm flex items-center gap-1.5"
                      disabled={createMut.isPending}
                      onClick={() => handleSaveNew(entry)}
                    >
                      {createMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      Save
                    </button>
                    <button className="btn-ghost text-sm" onClick={handleCancelForm}>Cancel</button>
                  </div>
                </VaultCard>
              );
            })()}

            {/* Configured cards */}
            {configuredEntries.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                {configuredEntries.map(entry => {
                  const ep = configuredByType[entry.adapter_type];
                  const tr = testResults[ep.endpoint_id];
                  const isEditing = editingId === ep.endpoint_id;
                  return (
                    <VaultCard key={entry.adapter_type} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${ep.enabled ? "bg-cold-teal" : "bg-dried-blood-bright"}`} />
                        <span className="text-sm font-heading font-semibold text-bone">{entry.label}</span>
                      </div>
                      <p className="text-xs text-bone-dim font-mono">{entry.description}</p>

                      {tr && (
                        <p className={`text-xs font-mono ${tr.success ? "text-cold-teal" : "text-dried-blood-bright"}`}>
                          {tr.success ? "Connected" : (tr.message ?? "Failed")}
                        </p>
                      )}

                      {/* Inline edit form */}
                      {isEditing && (() => {
                        const fields = getAdapterFields(ep.adapter_type);
                        return (
                          <div className="space-y-2 pt-2 border-t border-slate-border/30">
                            {fields.map(f => (
                              <div key={f.key}>
                                <label className="text-[10px] font-mono text-bone-muted block mb-1">{f.label}</label>
                                <input
                                  className="input-vault text-sm w-full"
                                  type={f.type ?? "text"}
                                  placeholder={f.placeholder}
                                  value={configForm[f.key] ?? ""}
                                  onChange={e => setConfigForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                                />
                                {f.hint && <p className="text-[9px] text-bone-dim font-mono mt-0.5 leading-tight">{f.hint}</p>}
                              </div>
                            ))}
                            <div className="flex gap-2 pt-1">
                              <button
                                className="btn-teal text-xs flex items-center gap-1"
                                disabled={updateMut.isPending}
                                onClick={() => handleSaveEdit(ep)}
                              >
                                {updateMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                Save
                              </button>
                              <button className="btn-ghost text-xs" onClick={handleCancelForm}>Cancel</button>
                            </div>
                          </div>
                        );
                      })()}

                      {/* Actions */}
                      {!isEditing && (
                        <div className="flex items-center gap-1.5 pt-1">
                          <button
                            className="btn-ghost text-xs py-1 px-2 flex items-center gap-1"
                            onClick={() => handleTest(ep)}
                            disabled={testMut.isPending}
                          >
                            <RefreshCw size={11} className={testMut.isPending ? "animate-spin" : ""} />
                            Test
                          </button>
                          <button
                            className="btn-ghost text-xs py-1 px-2 flex items-center gap-1"
                            onClick={() => handleStartEdit(ep)}
                          >
                            <Edit2 size={11} /> Edit
                          </button>
                          <button
                            className="btn-ghost text-xs py-1 px-2 text-dried-blood-bright flex items-center gap-1 ml-auto"
                            onClick={() => handleDelete(ep)}
                            disabled={deleteMut.isPending}
                          >
                            <Trash2 size={11} />
                          </button>
                        </div>
                      )}
                    </VaultCard>
                  );
                })}
              </div>
            ) : (
              !isPickerOpen && !isAddingInCategory && (
                <p className="text-xs text-bone-dim font-mono py-3 text-center">
                  No {CATEGORY_LABELS[category].toLowerCase()} configured — click Add to get started
                </p>
              )
            )}
          </div>
        );
      })}

      {/* ChatOps / Event Routing */}
      {(() => {
        const notifChannels = (integrations ?? []).filter(i => i.category === "notification_channels" && i.enabled);
        return (
          <VaultCard>
            <div className="flex items-center gap-2 mb-3">
              <Bell size={14} className="text-cold-teal" />
              <h2 className="vault-heading text-xs">ChatOps &amp; Event Routing</h2>
              {isRoutingDirty && (
                <button
                  className="btn-teal text-xs flex items-center gap-1 ml-auto"
                  onClick={() => saveRoutingMut.mutate({ routing }, { onSuccess: () => setIsRoutingDirty(false) })}
                  disabled={saveRoutingMut.isPending}
                >
                  {saveRoutingMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save
                </button>
              )}
            </div>

            {notifChannels.length === 0 ? (
              <p className="text-xs text-bone-dim font-mono">
                Add a notification channel above (Slack, Teams, Webhook, Email, or PagerDuty) to configure event routing.
              </p>
            ) : routingLoading ? (
              <div className="flex items-center gap-2 text-bone-muted text-xs font-mono py-4">
                <Loader2 size={12} className="animate-spin" /> Loading routing config...
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-border/30">
                      <th className="text-left text-bone-muted py-2 pr-6 font-normal">Event</th>
                      {notifChannels.map(ch => {
                        const entry = INTEGRATION_CATALOGUE.find(e => e.adapter_type === ch.adapter_type);
                        return (
                          <th key={ch.endpoint_id} className="text-center text-bone-muted py-2 px-3 font-normal">
                            {entry?.label ?? ch.adapter_type}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {EVENT_TYPES.map(event => (
                      <tr key={event} className="border-b border-slate-border/20 last:border-0">
                        <td className="py-2 pr-6 text-bone">{event}</td>
                        {notifChannels.map(ch => {
                          const isChecked = (routing[event] ?? []).includes(ch.adapter_type);
                          return (
                            <td key={ch.endpoint_id} className="py-2 px-3 text-center">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => toggleRoute(event, ch.adapter_type)}
                                className="accent-cold-teal cursor-pointer"
                              />
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-bone-dim font-mono mt-3">
                  Dashboard notifications are always active regardless of routing settings.
                </p>
              </div>
            )}
          </VaultCard>
        );
      })()}
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

// AIUC1_CATEGORY_LABELS removed — use FRAMEWORK_CONTROLS.aiuc1.categories[key].label instead.

/** Add Rule inline picker — supports framework_control_required (3-level cascade) and legacy aiuc1_control_required. */
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
  // framework_control_required cascade
  const [fwk, setFwk] = useState("");
  const [fwkCategory, setFwkCategory] = useState("");
  const [fwkControl, setFwkControl] = useState("");
  // legacy aiuc1_control_required
  const [legacyCategory, setLegacyCategory] = useState("");
  const [legacyControl, setLegacyControl] = useState("");

  const meta = GATE_RULE_TYPES.find((r) => r.value === selectedType);
  const isFwk = selectedType === "framework_control_required";
  const isLegacyAiuc1 = selectedType === "aiuc1_control_required";

  const fwkDef = fwk ? FRAMEWORK_CONTROLS[fwk] : undefined;
  const fwkCategoryDef = fwkDef && fwkCategory ? fwkDef.categories[fwkCategory] : undefined;

  const handleAdd = () => {
    if (!meta) return;
    const params: Record<string, unknown> = {};
    if (isFwk) {
      params["framework"] = fwk;
      params["category"] = fwkCategory;
      params["control"] = fwkControl;
    } else if (isLegacyAiuc1) {
      params["category"] = legacyCategory;
      params["control"] = legacyControl;
    }
    const description = isFwk
      ? `${FRAMEWORK_CONTROLS[fwk]?.label ?? fwk} / ${fwkCategoryDef?.label ?? fwkCategory} / ${fwkCategoryDef?.controls[fwkControl]?.label ?? fwkControl}`
      : isLegacyAiuc1 && legacyCategory && legacyControl
      ? `AIUC-1 / ${FRAMEWORK_CONTROLS.aiuc1?.categories[legacyCategory]?.label ?? legacyCategory} / ${fieldKeyToAiuc1Label(legacyControl)}`
      : meta.label;
    onAdd({
      rule_id: `rule_${selectedType}_${Date.now()}`,
      rule_type: selectedType,
      description,
      required: true,
      ai_only: meta.aiOnly || aiOnly || (isFwk && !!(fwkDef?.aiOnly)),
      threshold: meta.hasThreshold && threshold !== "" ? Number(threshold) : null,
      parameters: meta.hasParams ? params : undefined,
    });
  };

  const isAddDisabled =
    !selectedType ||
    (isFwk && (!fwk || !fwkCategory || !fwkControl)) ||
    (isLegacyAiuc1 && (!legacyCategory || !legacyControl));

  const groups = [...new Set(GATE_RULE_TYPES.map((r) => r.group))];

  return (
    <div className="mt-3 p-3 border border-clinical-cyan/30 rounded bg-vault-black/50 space-y-3">
      <div className="text-xs font-mono text-clinical-cyan font-semibold">Add Rule</div>

      {/* Rule type selector */}
      <select
        className="input-vault text-xs w-full"
        value={selectedType}
        onChange={(e) => {
          setSelectedType(e.target.value);
          const m = GATE_RULE_TYPES.find((r) => r.value === e.target.value);
          if (m) setAiOnly(m.aiOnly);
          setFwk(""); setFwkCategory(""); setFwkControl("");
          setLegacyCategory(""); setLegacyControl("");
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

      {/* Threshold input */}
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

      {/* Framework / Category / Control cascade for framework_control_required */}
      {isFwk && (
        <div className="space-y-2">
          {/* Framework select */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Framework</label>
            <select
              className="input-vault text-xs flex-1"
              value={fwk}
              onChange={(e) => { setFwk(e.target.value); setFwkCategory(""); setFwkControl(""); }}
            >
              <option value="">Select framework…</option>
              {Object.entries(FRAMEWORK_CONTROLS).map(([key, def]) => (
                <option key={key} value={key}>{def.label}</option>
              ))}
            </select>
          </div>
          {/* Category select */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Category</label>
            <select
              className="input-vault text-xs flex-1"
              value={fwkCategory}
              onChange={(e) => { setFwkCategory(e.target.value); setFwkControl(""); }}
              disabled={!fwk}
            >
              <option value="">Select category…</option>
              {fwkDef && Object.entries(fwkDef.categories).map(([key, cat]) => (
                <option key={key} value={key}>{cat.label}</option>
              ))}
            </select>
          </div>
          {/* Control select */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Control</label>
            <select
              className="input-vault text-xs flex-1"
              value={fwkControl}
              onChange={(e) => setFwkControl(e.target.value)}
              disabled={!fwkCategory}
            >
              <option value="">Select control…</option>
              {fwkCategoryDef && Object.entries(fwkCategoryDef.controls).map(([key, ctrl]) => (
                <option key={key} value={key}>{ctrl.label}</option>
              ))}
            </select>
          </div>
          {/* Evidence type hint */}
          {fwkControl && fwkCategoryDef?.controls[fwkControl] && (
            <div className="text-xs font-mono text-bone-muted/60 pl-28">
              Evidence: <span className="text-cold-teal">{fwkCategoryDef.controls[fwkControl].evidenceType}</span>
              {fwkCategoryDef.controls[fwkControl].description && (
                <> — {fwkCategoryDef.controls[fwkControl].description}</>
              )}
            </div>
          )}
        </div>
      )}

      {/* Legacy AIUC-1 cascade (aiuc1_control_required) */}
      {isLegacyAiuc1 && (
        <div className="space-y-2">
          <div className="text-xs font-mono text-amber-400/70">Legacy — use Framework Control Required instead</div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Category</label>
            <select
              className="input-vault text-xs flex-1"
              value={legacyCategory}
              onChange={(e) => { setLegacyCategory(e.target.value); setLegacyControl(""); }}
            >
              <option value="">Select category…</option>
              {Object.keys(AIUC1_CONTROLS).map((cat) => (
                <option key={cat} value={cat}>
                  {FRAMEWORK_CONTROLS.aiuc1?.categories[cat]?.label ?? cat}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-bone-muted w-24">Control</label>
            <select
              className="input-vault text-xs flex-1"
              value={legacyControl}
              onChange={(e) => setLegacyControl(e.target.value)}
              disabled={!legacyCategory}
            >
              <option value="">Select control…</option>
              {(AIUC1_CONTROLS[legacyCategory] ?? []).map((k) => (
                <option key={k} value={k}>{fieldKeyToAiuc1Label(k)}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* AI-only toggle (only for non-ai-only rule types) */}
      {meta && !meta.aiOnly && !isFwk && (
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
          disabled={isAddDisabled}
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

/** Fallback environments used when pipeline hasn't loaded */

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
  const [activeTab, setActiveTab] = useState<Tab>("gates");

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
      {activeTab === "gates" && <GateRulesTab />}
      {activeTab === "environments" && <EnvironmentsTab />}
      {activeTab === "business_units" && <AdminBusinessUnitsPage />}
      {activeTab === "integrations" && <IntegrationsTab />}
      {activeTab === "project_data" && <AdminProjectsPage />}
    </div>
  );
}
