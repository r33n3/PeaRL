import { useState } from "react";
import { Building2, Plus, Trash2, Cpu, ChevronDown, ChevronRight, Users } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import { MonoText } from "@/components/shared/MonoText";
import {
  useBusinessUnits,
  useCreateBU,
  useDeleteBU,
  useSetBUFrameworks,
  useBUBaseline,
  useDeleteBUBaseline,
  useAssignProjectToBU,
} from "@/api/business_units";
import { useProjects } from "@/api/dashboard";
import { FRAMEWORK_CONTROLS } from "@/lib/frameworkControls";

const FRAMEWORK_KEYS = Object.keys(FRAMEWORK_CONTROLS);

const DEFAULT_ORG_ID = "org_default";

function BUBaselineSection({ buId }: { buId: string }) {
  const { data, isLoading } = useBUBaseline(buId);
  const deleteBaseline = useDeleteBUBaseline();

  if (isLoading) return <p className="text-[10px] font-mono text-bone-dim mt-2">Loading baseline…</p>;

  const inherits = !data || data.inherits_org;
  const baseline = data?.baseline;

  return (
    <div className="mt-3 pt-3 border-t border-slate-border/40">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-heading uppercase tracking-wider text-bone-muted">Baseline</span>
        {!inherits && (
          <button
            className="text-[10px] font-mono text-bone-dim hover:text-dried-blood-bright transition-colors"
            onClick={() => deleteBaseline.mutate(buId)}
            disabled={deleteBaseline.isPending}
          >
            Reset to org
          </button>
        )}
      </div>
      {inherits ? (
        <p className="text-[10px] font-mono text-bone-dim italic mt-1">Inheriting org baseline</p>
      ) : (
        <div className="mt-1 flex flex-wrap gap-1">
          {Object.entries(baseline?.defaults ?? {}).map(([domain, controls]) => {
            const vals = Object.values(controls as Record<string, unknown>);
            const enabled = vals.filter((v) => v === true).length;
            const total = vals.length;
            const pct = total > 0 ? Math.round((enabled / total) * 100) : 0;
            const domainLabels: Record<string, string> = {
              data_privacy: "Privacy", security: "Security", safety: "Safety",
              reliability: "Reliability", accountability: "Accountability", society: "Society",
            };
            return (
              <span key={domain} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-wet-stone border border-slate-border text-bone-dim">
                {domainLabels[domain] ?? domain} {pct}%
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BUProjectsSection({ buId, buName }: { buId: string; buName: string }) {
  const { data: projects = [] } = useProjects();
  const assignMut = useAssignProjectToBU();
  const [expanded, setExpanded] = useState(false);

  const assigned = projects.filter((p: { bu_id?: string | null }) => p.bu_id === buId);
  const unassigned = projects.filter((p: { bu_id?: string | null }) => !p.bu_id || p.bu_id !== buId);

  return (
    <div className="mt-3 pt-3 border-t border-slate-border/40">
      <button
        className="flex items-center gap-1 text-[10px] font-heading uppercase tracking-wider text-bone-muted w-full"
        onClick={() => setExpanded((e) => !e)}
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <Users size={10} />
        Projects ({assigned.length})
      </button>
      {expanded && (
        <div className="mt-2 space-y-1.5">
          {assigned.length === 0 && (
            <p className="text-[10px] font-mono text-bone-dim italic">No projects assigned</p>
          )}
          {assigned.map((p: { project_id: string; name: string }) => (
            <div key={p.project_id} className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-bone">{p.name}</span>
              <button
                className="text-[10px] font-mono text-bone-dim hover:text-dried-blood-bright"
                onClick={() => assignMut.mutate({ projectId: p.project_id, buId: null })}
              >
                Remove
              </button>
            </div>
          ))}
          {unassigned.length > 0 && (
            <select
              className="input-vault w-full text-[10px] mt-1"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) {
                  assignMut.mutate({ projectId: e.target.value, buId });
                  e.target.value = "";
                }
              }}
            >
              <option value="" disabled>Assign a project…</option>
              {unassigned.map((p: { project_id: string; name: string }) => (
                <option key={p.project_id} value={p.project_id}>{p.name}</option>
              ))}
            </select>
          )}
        </div>
      )}
    </div>
  );
}

export function AdminBusinessUnitsPage() {
  const { data: bus = [], isLoading } = useBusinessUnits();
  const createBU = useCreateBU();
  const deleteBU = useDeleteBU();
  const setFrameworks = useSetBUFrameworks();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: "",
    description: "",
    org_id: DEFAULT_ORG_ID,
    framework_selections: [] as string[],
  });

  const [derivingFor, setDerivingFor] = useState<string | null>(null);

  function toggleFramework(key: string) {
    setForm((f) => ({
      ...f,
      framework_selections: f.framework_selections.includes(key)
        ? f.framework_selections.filter((k) => k !== key)
        : [...f.framework_selections, key],
    }));
  }

  async function handleCreate() {
    if (!form.name.trim()) return;
    await createBU.mutateAsync({
      org_id: form.org_id,
      name: form.name,
      description: form.description || undefined,
      framework_selections: form.framework_selections,
    });
    setForm({ name: "", description: "", org_id: DEFAULT_ORG_ID, framework_selections: [] });
    setShowCreate(false);
  }

  async function handleDeriveRequirements(buId: string, currentFrameworks: string[]) {
    setDerivingFor(buId);
    try {
      await setFrameworks.mutateAsync({ buId, framework_selections: currentFrameworks });
    } finally {
      setDerivingFor(null);
    }
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">Business Units</h1>
          <p className="text-sm font-mono text-bone-dim mt-1">
            Manage business units and their framework compliance requirements.
          </p>
        </div>
        <button className="btn-teal" onClick={() => setShowCreate(!showCreate)}>
          <Plus size={14} /> New Business Unit
        </button>
      </div>

      {showCreate && (
        <VaultCard className="mb-6 border border-cold-teal/20">
          <h2 className="vault-heading text-sm mb-4">Create Business Unit</h2>
          <div className="space-y-3">
            <div>
              <label className="text-[10px] font-heading uppercase text-bone-dim block mb-1">Name *</label>
              <input
                className="input-vault w-full"
                placeholder="Engineering"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-[10px] font-heading uppercase text-bone-dim block mb-1">Description</label>
              <input
                className="input-vault w-full"
                placeholder="Optional description"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-[10px] font-heading uppercase text-bone-dim block mb-2">
                Frameworks
              </label>
              <div className="flex flex-wrap gap-2">
                {FRAMEWORK_KEYS.map((key) => {
                  const fw = FRAMEWORK_CONTROLS[key as keyof typeof FRAMEWORK_CONTROLS];
                  const selected = form.framework_selections.includes(key);
                  return (
                    <button
                      key={key}
                      onClick={() => toggleFramework(key)}
                      className={`text-xs font-mono px-2.5 py-1 rounded border transition-all ${
                        selected
                          ? "bg-cold-teal/10 border-cold-teal/40 text-cold-teal"
                          : "bg-wet-stone border-slate-border text-bone-dim hover:text-bone"
                      }`}
                    >
                      {fw?.label ?? key}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <button className="btn-teal" onClick={handleCreate} disabled={createBU.isPending}>
                {createBU.isPending ? "Creating…" : "Create"}
              </button>
              <button className="btn-ghost" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
            </div>
          </div>
        </VaultCard>
      )}

      {isLoading && (
        <p className="text-sm font-mono text-bone-dim">Loading business units…</p>
      )}

      <div className="space-y-3">
        {bus.map((bu) => (
          <VaultCard key={bu.bu_id} className="border border-slate-border/60">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <Building2 size={16} className="text-clinical-cyan" />
                <div>
                  <p className="font-heading font-semibold text-sm text-bone">{bu.name}</p>
                  <MonoText className="text-[10px] text-bone-dim">{bu.bu_id}</MonoText>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="btn-ghost text-xs flex items-center gap-1"
                  onClick={() => handleDeriveRequirements(bu.bu_id, bu.framework_selections)}
                  disabled={derivingFor === bu.bu_id || bu.framework_selections.length === 0}
                  title="Derive requirements from frameworks"
                >
                  <Cpu size={12} />
                  {derivingFor === bu.bu_id ? "Deriving…" : "Derive Reqs"}
                </button>
                <button
                  className="btn-ghost text-xs text-dried-blood-bright hover:bg-dried-blood-bright/10"
                  onClick={() => deleteBU.mutate(bu.bu_id)}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            {bu.description && (
              <p className="text-xs font-mono text-bone-muted mt-2">{bu.description}</p>
            )}
            {bu.framework_selections.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {bu.framework_selections.map((fw) => (
                  <span key={fw} className="text-[10px] font-mono px-2 py-0.5 rounded bg-wet-stone border border-slate-border text-bone-dim">
                    {FRAMEWORK_CONTROLS[fw as keyof typeof FRAMEWORK_CONTROLS]?.label ?? fw}
                  </span>
                ))}
              </div>
            )}
            <BUBaselineSection buId={bu.bu_id} />
            <BUProjectsSection buId={bu.bu_id} buName={bu.name} />
          </VaultCard>
        ))}
        {!isLoading && bus.length === 0 && (
          <p className="text-sm font-mono text-bone-dim text-center py-8">
            No business units yet. Create one to start enforcing framework controls.
          </p>
        )}
      </div>
    </div>
  );
}
