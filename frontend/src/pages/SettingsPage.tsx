import { useState, useEffect, useMemo } from "react";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { MonoText } from "@/components/shared/MonoText";
import {
  useGates,
  useUpdateGateRules,
  useUpdateGateApprovalMode,
} from "@/api/promotions";
import type { GateData, GateRuleData } from "@/api/promotions";
import {
  useIntegrations,
  useCreateIntegration,
  useDeleteIntegration,
  useTestIntegration,
} from "@/api/integrations";
import { useOrgBaseline, useSaveOrgBaseline } from "@/api/settings";
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
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Tab = "integrations" | "gates" | "baseline" | "notifications";

const TABS: { key: Tab; icon: typeof Plug; label: string }[] = [
  { key: "integrations", icon: Plug, label: "Integrations" },
  { key: "gates", icon: ShieldCheck, label: "Gate Rules" },
  { key: "baseline", icon: FileCode, label: "Org Baseline" },
  { key: "notifications", icon: Bell, label: "Notifications" },
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

function GateCard({
  gate,
  localState,
  onToggleRule,
  onThresholdChange,
  onSave,
  onToggleApproval,
  isSaving,
}: {
  gate: GateData;
  localState: LocalGateState;
  onToggleRule: (ruleId: string) => void;
  onThresholdChange: (ruleId: string, val: number | null) => void;
  onSave: () => void;
  onToggleApproval: () => void;
  isSaving: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

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
              unsaved changes
            </span>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleApproval();
          }}
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
      </div>

      {/* Expanded rule list */}
      {expanded && (
        <div className="mt-4 space-y-2">
          {localState.rules.length === 0 ? (
            <p className="text-bone-dim font-mono text-xs py-3 text-center">
              No rules configured for this gate
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
              </div>
            ))
          )}

          {/* Save button */}
          {localState.rules.length > 0 && (
            <div className="flex items-center justify-end pt-2">
              <button
                className="btn-teal text-sm flex items-center gap-1.5"
                disabled={!localState.dirty || isSaving}
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
  const updateRulesMut = useUpdateGateRules();
  const updateModeMut = useUpdateGateApprovalMode();

  // Local editable state keyed by gate_id
  const [localGates, setLocalGates] = useState<
    Record<string, LocalGateState>
  >({});

  // Initialise local state when gates load
  useEffect(() => {
    if (!gates) return;
    setLocalGates((prev) => {
      const next: Record<string, LocalGateState> = {};
      for (const g of gates) {
        const existing = prev[g.gate_id];
        if (existing && existing.dirty) {
          // preserve unsaved edits
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

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-6 justify-center">
        <Loader2 size={16} className="animate-spin" /> Loading gate rules...
      </div>
    );
  }

  if (!gates || gates.length === 0) {
    return (
      <VaultCard className="text-center py-8">
        <ShieldCheck size={24} className="text-bone-dim mx-auto mb-2" />
        <p className="text-bone-dim font-mono text-sm">
          No promotion gates configured
        </p>
      </VaultCard>
    );
  }

  return (
    <div className="space-y-4">
      {gates.map((gate) => (
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
          isSaving={updateRulesMut.isPending}
        />
      ))}
    </div>
  );
}

/* ================================================================== */
/*  TAB 3 -- Org Baseline                                             */
/* ================================================================== */

const BASELINE_CATEGORIES = [
  "coding",
  "logging",
  "iam",
  "network",
  "responsible_ai",
  "testing",
] as const;

function BaselineTab() {
  const [projectId, setProjectId] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editedDefaults, setEditedDefaults] = useState<
    Record<string, Record<string, unknown>> | null
  >(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set()
  );

  const {
    data: baseline,
    isLoading,
    isError,
  } = useOrgBaseline(projectId);
  const saveMut = useSaveOrgBaseline();

  // Reset edit state when baseline or project changes
  useEffect(() => {
    setEditMode(false);
    setEditedDefaults(null);
  }, [projectId, baseline]);

  const toggleSection = (cat: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
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
    setEditMode(true);
  };

  const handleFieldChange = (
    category: string,
    field: string,
    value: boolean | null
  ) => {
    setEditedDefaults((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [category]: {
          ...prev[category],
          [field]: value,
        },
      };
    });
  };

  const handleSave = () => {
    if (!baseline || !editedDefaults) return;
    saveMut.mutate(
      {
        projectId,
        data: {
          schema_version: "1.1",
          kind: "PearlOrgBaseline",
          baseline_id: baseline.baseline_id,
          org_name: baseline.org_name,
          defaults: editedDefaults,
        },
      },
      {
        onSuccess: () => {
          setEditMode(false);
          setEditedDefaults(null);
        },
      }
    );
  };

  const currentDefaults = editMode && editedDefaults ? editedDefaults : baseline?.defaults;

  // Determine which categories exist in the data
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
          {categories.map((cat) => {
            const fields = currentDefaults?.[cat] ?? {};
            const isExpanded = expandedSections.has(cat);
            return (
              <VaultCard key={cat}>
                <div
                  className="flex items-center gap-2 cursor-pointer select-none"
                  onClick={() => toggleSection(cat)}
                >
                  {isExpanded ? (
                    <ChevronDown size={14} className="text-bone-muted" />
                  ) : (
                    <ChevronRight size={14} className="text-bone-muted" />
                  )}
                  <h3 className="vault-heading text-xs">{humanize(cat)}</h3>
                  <span className="text-[10px] text-bone-dim font-mono ml-auto">
                    {Object.keys(fields).length} fields
                  </span>
                </div>
                {isExpanded && (
                  <div className="mt-3 space-y-1">
                    {Object.entries(fields).map(([fieldKey, fieldVal]) => (
                      <div
                        key={fieldKey}
                        className="flex items-center justify-between px-3 py-2 bg-vault-black/50 rounded"
                      >
                        <span className="text-xs text-bone font-mono">
                          {humanize(fieldKey)}
                        </span>
                        {editMode ? (
                          <button
                            className="p-1 rounded hover:bg-charcoal transition-colors"
                            onClick={() =>
                              handleFieldChange(
                                cat,
                                fieldKey,
                                triStateNext(fieldVal)
                              )
                            }
                            title="Click to toggle: true / false / null"
                          >
                            {renderValue(fieldVal)}
                          </button>
                        ) : (
                          renderValue(fieldVal)
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </VaultCard>
            );
          })}
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
    </div>
  );
}
