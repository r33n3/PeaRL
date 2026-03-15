import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  usePolicyBaselines,
  useOrgBaseline,
  useBaselineControls,
  useSaveOrgBaseline,
} from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { MonoText } from "@/components/shared/MonoText";
import {
  BookLock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Globe,
  ChevronDown,
  ChevronRight,
  Check,
  Minus,
  AlertOctagon,
  Pencil,
  Save,
  X,
} from "lucide-react";
import type { OrgBaseline, ProjectBaselineStatus } from "@/lib/types";

const DOMAIN_LABELS: Record<string, string> = {
  data_privacy: "Privacy",
  security: "Security",
  safety: "Safety",
  reliability: "Reliability",
  accountability: "Accountability",
  society: "Society",
};

/* ------------------------------------------------------------------ */
/*  Domain pill + expandable control list (read-only)                  */
/* ------------------------------------------------------------------ */

function DomainPill({
  domainKey,
  pct,
  enabled,
  total,
  controls,
  isActive,
  onToggle,
}: {
  domainKey: string;
  pct: number;
  enabled: number;
  total: number;
  controls: { id: string; active: boolean; mandatory?: boolean }[];
  isActive: boolean;
  onToggle: () => void;
}) {
  const colorClass =
    pct >= 75
      ? "border-cold-teal/30 text-cold-teal bg-cold-teal/10 hover:bg-cold-teal/20"
      : pct >= 40
        ? "border-amber-500/30 text-amber-400 bg-amber-500/10 hover:bg-amber-500/20"
        : "border-slate-border text-bone-dim bg-wet-stone hover:bg-slate-border/40";

  return (
    <button
      onClick={onToggle}
      className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors cursor-pointer ${colorClass} ${isActive ? "ring-1 ring-offset-1 ring-offset-deep-bg ring-cold-teal/40" : ""}`}
      title={`${enabled}/${total} controls enabled — click to expand`}
    >
      {DOMAIN_LABELS[domainKey] ?? domainKey} {pct}%
      {isActive ? <ChevronDown size={9} /> : <ChevronRight size={9} />}
    </button>
  );
}

function ControlList({
  controls,
}: {
  controls: { id: string; active: boolean; mandatory?: boolean }[];
}) {
  const enabled = controls.filter((c) => c.active);
  const remaining = controls.filter((c) => !c.active);

  return (
    <div className="mt-2 mb-1 bg-wet-stone rounded border border-slate-border p-3 space-y-2 text-[10px] font-mono">
      {enabled.length > 0 && (
        <div>
          <p className="text-bone-dim uppercase tracking-wider mb-1">Enabled ({enabled.length})</p>
          <div className="space-y-0.5">
            {enabled.map((c) => (
              <div key={c.id} className="flex items-center gap-1.5 text-cold-teal">
                <Check size={9} className="shrink-0" />
                <span>{c.id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {remaining.length > 0 && (
        <div>
          <p className="text-bone-dim uppercase tracking-wider mb-1">
            Remaining / Disabled ({remaining.length})
          </p>
          <div className="space-y-0.5">
            {remaining.map((c) => (
              <div
                key={c.id}
                className={`flex items-center gap-1.5 ${c.mandatory ? "text-red-400" : "text-bone-dim"}`}
              >
                {c.mandatory ? (
                  <AlertOctagon size={9} className="shrink-0" />
                ) : (
                  <Minus size={9} className="shrink-0" />
                )}
                <span>{c.id}</span>
                {c.mandatory && (
                  <span className="text-red-400/70 ml-1">mandatory</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {controls.length === 0 && (
        <p className="text-bone-dim italic">No controls defined for this domain</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Edit panel — per-control toggles for one domain                    */
/* ------------------------------------------------------------------ */

function ControlToggleList({
  domainKey,
  controls,
  mandatoryKeys,
  controlLabels,
  onToggle,
}: {
  domainKey: string;
  controls: Record<string, boolean>;
  mandatoryKeys: Set<string>;
  controlLabels: Record<string, string>;
  onToggle: (controlId: string) => void;
}) {
  return (
    <div className="mt-2 mb-1 bg-wet-stone rounded border border-slate-border p-3 space-y-1.5">
      {Object.entries(controls).map(([ctrlId, enabled]) => {
        const fullKey = `${domainKey}.${ctrlId}`;
        const isMandatory = mandatoryKeys.has(fullKey);
        const label = controlLabels[fullKey] ?? ctrlId;

        return (
          <div key={ctrlId} className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 min-w-0">
              {isMandatory && (
                <AlertOctagon size={9} className="text-amber-400 shrink-0" />
              )}
              <span className="text-[10px] font-mono text-bone-dim truncate" title={label}>
                {label}
              </span>
            </div>
            <button
              onClick={() => !isMandatory && onToggle(ctrlId)}
              disabled={isMandatory}
              title={isMandatory ? "Mandatory control — cannot be disabled" : undefined}
              className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full border transition-colors ${
                enabled
                  ? "bg-cold-teal/70 border-cold-teal/50"
                  : "bg-wet-stone border-slate-border"
              } ${isMandatory ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full bg-white shadow transition-transform ${
                  enabled ? "translate-x-3" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Org Baseline card                                                   */
/* ------------------------------------------------------------------ */

function OrgBaselineCard({
  orgBaseline,
  inheritingCount,
}: {
  orgBaseline: OrgBaseline;
  inheritingCount: number;
}) {
  const [activeDomain, setActiveDomain] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, Record<string, boolean>>>({});

  const { data: controlsData } = useBaselineControls();
  const saveMutation = useSaveOrgBaseline();

  const defaults = orgBaseline.defaults as Record<string, Record<string, boolean | null>>;

  const orgDomains = Object.entries(defaults).map(([key, controls]) => {
    const controlList = Object.entries(controls).map(([id, v]) => ({
      id,
      active: v === true,
    }));
    const enabled = controlList.filter((c) => c.active).length;
    const total = controlList.length;
    const pct = total > 0 ? Math.round((enabled / total) * 100) : 0;
    return { key, enabled, total, pct, controlList };
  });

  function startEdit() {
    // Deep copy defaults into draft (coerce null → false)
    const d: Record<string, Record<string, boolean>> = {};
    for (const [domain, controls] of Object.entries(defaults)) {
      d[domain] = {};
      for (const [ctrlId, val] of Object.entries(controls)) {
        d[domain][ctrlId] = val === true;
      }
    }
    setDraft(d);
    setActiveDomain(Object.keys(defaults)[0] ?? null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setDraft({});
  }

  function toggleControl(domain: string, ctrlId: string) {
    setDraft((prev) => ({
      ...prev,
      [domain]: { ...prev[domain], [ctrlId]: !prev[domain][ctrlId] },
    }));
  }

  async function saveBaseline() {
    await saveMutation.mutateAsync({
      ...orgBaseline,
      defaults: draft,
    } as Record<string, unknown>);
    setEditing(false);
    setDraft({});
  }

  const mandatoryKeys = new Set(controlsData?.mandatory.essential ?? []);
  const controlLabels = controlsData?.controls ?? {};

  return (
    <VaultCard className="mb-6 border-cold-teal/20">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Globe size={16} className="text-cold-teal shrink-0" />
          <div>
            <h2 className="font-heading font-semibold text-bone">Organizational Baseline</h2>
            <MonoText className="text-xs">{orgBaseline.org_name} · {orgBaseline.baseline_id}</MonoText>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-cold-teal bg-cold-teal/10 border border-cold-teal/30 px-1.5 py-0.5 rounded">
            Shared by {inheritingCount} project{inheritingCount !== 1 ? "s" : ""}
          </span>
          {!editing ? (
            <button
              onClick={startEdit}
              className="flex items-center gap-1 text-[10px] font-mono text-bone-dim hover:text-bone border border-slate-border hover:border-cold-teal/40 px-1.5 py-0.5 rounded transition-colors"
            >
              <Pencil size={9} /> Edit
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <button
                onClick={saveBaseline}
                disabled={saveMutation.isPending}
                className="flex items-center gap-1 text-[10px] font-mono text-cold-teal border border-cold-teal/40 bg-cold-teal/10 hover:bg-cold-teal/20 px-1.5 py-0.5 rounded transition-colors disabled:opacity-50"
              >
                <Save size={9} /> {saveMutation.isPending ? "Saving…" : "Save"}
              </button>
              <button
                onClick={cancelEdit}
                className="flex items-center gap-1 text-[10px] font-mono text-bone-dim hover:text-bone border border-slate-border px-1.5 py-0.5 rounded transition-colors"
              >
                <X size={9} /> Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Domain tabs */}
      <div className="flex flex-wrap gap-1">
        {editing
          ? Object.keys(draft).map((domainKey) => {
              const controls = draft[domainKey];
              const total = Object.keys(controls).length;
              const enabled = Object.values(controls).filter(Boolean).length;
              const pct = total > 0 ? Math.round((enabled / total) * 100) : 0;
              const colorClass =
                pct >= 75
                  ? "border-cold-teal/30 text-cold-teal bg-cold-teal/10 hover:bg-cold-teal/20"
                  : pct >= 40
                    ? "border-amber-500/30 text-amber-400 bg-amber-500/10 hover:bg-amber-500/20"
                    : "border-slate-border text-bone-dim bg-wet-stone hover:bg-slate-border/40";
              return (
                <button
                  key={domainKey}
                  onClick={() => setActiveDomain((p) => (p === domainKey ? null : domainKey))}
                  className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${colorClass} ${activeDomain === domainKey ? "ring-1 ring-offset-1 ring-offset-deep-bg ring-cold-teal/40" : ""}`}
                >
                  {DOMAIN_LABELS[domainKey] ?? domainKey} {pct}%
                  {activeDomain === domainKey ? <ChevronDown size={9} /> : <ChevronRight size={9} />}
                </button>
              );
            })
          : orgDomains.map(({ key, enabled, total, pct, controlList }) => (
              <DomainPill
                key={key}
                domainKey={key}
                pct={pct}
                enabled={enabled}
                total={total}
                controls={controlList}
                isActive={activeDomain === key}
                onToggle={() => setActiveDomain((prev) => (prev === key ? null : key))}
              />
            ))}
      </div>

      {/* Expanded panel */}
      {activeDomain && (
        editing ? (
          <ControlToggleList
            domainKey={activeDomain}
            controls={draft[activeDomain] ?? {}}
            mandatoryKeys={mandatoryKeys}
            controlLabels={controlLabels}
            onToggle={(ctrlId) => toggleControl(activeDomain, ctrlId)}
          />
        ) : (
          (() => {
            const d = orgDomains.find((x) => x.key === activeDomain);
            return d ? <ControlList controls={d.controlList} /> : null;
          })()
        )
      )}

      {saveMutation.isError && (
        <p className="mt-2 text-[10px] font-mono text-red-400">
          Save failed — check your permissions or try again.
        </p>
      )}
    </VaultCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Project Baseline card                                              */
/* ------------------------------------------------------------------ */

function BaselineCard({
  p,
  orgBaseline,
  onExceptionClick,
}: {
  p: ProjectBaselineStatus;
  orgBaseline: OrgBaseline | undefined;
  onExceptionClick: (id: string) => void;
}) {
  const [activeDomain, setActiveDomain] = useState<string | null>(null);

  const domains = Object.entries(p.domain_summary);
  const totalEnabled = domains.reduce((s, [, d]) => s + d.enabled, 0);
  const totalControls = domains.reduce((s, [, d]) => s + d.total, 0);
  const coveragePct = totalControls > 0 ? Math.round((totalEnabled / totalControls) * 100) : 0;

  const orgDefaults = orgBaseline?.defaults as
    | Record<string, Record<string, boolean | null>>
    | undefined;

  function buildControlList(domainKey: string): { id: string; active: boolean; mandatory?: boolean }[] {
    if (!orgDefaults?.[domainKey]) return [];
    return Object.entries(orgDefaults[domainKey]).map(([id, v]) => {
      const excludedByProject = p.scope_exclusions.includes(id);
      const isMandatory = p.mandatory_controls.includes(id);
      const active = v === true && !excludedByProject;
      return { id, active, mandatory: isMandatory };
    });
  }

  return (
    <VaultCard className={!p.baseline_configured ? "border-red-500/30" : totalControls === 0 ? "border-amber-500/20" : ""}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-heading font-semibold text-bone">{p.name}</h3>
          <MonoText className="text-xs">{p.project_id}</MonoText>
        </div>
        {p.baseline_configured ? (
          <CheckCircle size={16} className="text-cold-teal shrink-0 mt-0.5" />
        ) : (
          <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
        )}
      </div>

      {p.baseline_configured ? (
        <>
          <div className="flex items-center justify-between text-[10px] font-mono text-bone-dim mb-1">
            <span>{totalControls === 0 ? "No controls defined" : `${coveragePct}% enabled`}</span>
          </div>
          <div className="h-1.5 bg-wet-stone rounded-full overflow-hidden mb-3">
            <div className="h-full bg-cold-teal/70 rounded-full" style={{ width: `${coveragePct}%` }} />
          </div>

          {domains.length === 0 ? (
            <p className="text-[10px] font-mono text-bone-dim italic mb-1">No domain controls defined in baseline</p>
          ) : (
            <div className="flex flex-wrap gap-1 mb-1">
              {domains.map(([key, d]) => {
                const pct = d.total > 0 ? Math.round((d.enabled / d.total) * 100) : 0;
                const controls = buildControlList(key);
                return (
                  <DomainPill
                    key={key}
                    domainKey={key}
                    pct={pct}
                    enabled={d.enabled}
                    total={d.total}
                    controls={controls}
                    isActive={activeDomain === key}
                    onToggle={() => setActiveDomain((prev) => (prev === key ? null : key))}
                  />
                );
              })}
            </div>
          )}

          {activeDomain && (() => {
            const controls = buildControlList(activeDomain);
            return controls.length > 0 ? <ControlList controls={controls} /> : null;
          })()}

          <div className="mb-2 mt-2">
            {p.baseline_source === "bu" ? (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-cold-teal/30 text-cold-teal bg-cold-teal/10">
                {p.org_name ?? "Org"} · {p.bu_name}
              </span>
            ) : p.baseline_source === "project" ? (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-cold-teal/30 text-cold-teal bg-cold-teal/10">Custom baseline</span>
            ) : (
              <span className="text-[10px] font-mono text-bone-dim italic">{p.org_name ?? "Org baseline"}</span>
            )}
          </div>

          {p.scope_exclusions.length > 0 && (
            <details className="mb-2">
              <summary className="text-[10px] font-mono text-amber-400 cursor-pointer select-none">
                {p.scope_exclusions.length} scope exclusion{p.scope_exclusions.length !== 1 ? "s" : ""}
              </summary>
              <ul className="mt-1 space-y-0.5 pl-2">
                {p.scope_exclusions.map((ctrl) => {
                  const isMandatory = p.mandatory_controls.includes(ctrl);
                  return (
                    <li key={ctrl} className="flex items-center gap-1 text-[10px] font-mono">
                      <span className={isMandatory ? "text-red-400" : "text-bone-dim"}>{ctrl}</span>
                      {isMandatory && <span className="text-red-400 ml-1">mandatory</span>}
                    </li>
                  );
                })}
              </ul>
            </details>
          )}

          {(p.active_exceptions > 0 || p.pending_exceptions > 0) ? (
            <div className="border-t border-slate-border pt-2 space-y-1">
              {p.exceptions.slice(0, 3).map((e) => (
                <button
                  key={e.exception_id}
                  onClick={() => onExceptionClick(e.exception_id)}
                  className="w-full text-left flex items-center justify-between group"
                >
                  <span className="text-[10px] font-mono text-bone-dim truncate group-hover:text-bone transition-colors">
                    {e.rationale?.slice(0, 60) ?? e.exception_id}
                  </span>
                  <span className={`text-[10px] font-mono ml-2 shrink-0 ${
                    e.status === "active" ? "text-cold-teal" : "text-amber-400"
                  }`}>
                    {e.status}
                  </span>
                </button>
              ))}
              {p.exceptions.length > 3 && (
                <p className="text-[10px] font-mono text-bone-dim">+{p.exceptions.length - 3} more</p>
              )}
            </div>
          ) : (
            <p className="text-[10px] font-mono text-bone-dim">No active exceptions</p>
          )}
        </>
      ) : (
        <p className="text-xs font-mono text-red-400/80">
          No org baseline configured — compileContext will fail until one is attached.
        </p>
      )}
    </VaultCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export function PolicyPage() {
  const navigate = useNavigate();
  const { data: baselines, isLoading } = usePolicyBaselines();
  const { data: orgBaseline } = useOrgBaseline();

  const configured = baselines?.filter((p) => p.baseline_configured) ?? [];
  const missing = baselines?.filter((p) => !p.baseline_configured) ?? [];
  const totalExceptions =
    baselines?.reduce((s, p) => s + p.active_exceptions + p.pending_exceptions, 0) ?? 0;
  const inheritingCount = baselines?.filter((p) => p.inherits_org_baseline).length ?? 0;

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Policy Baselines</h1>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <VaultCard className="flex items-center gap-4">
          <div className="p-2 rounded-md bg-cold-teal/10">
            <BookLock size={20} className="text-cold-teal" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{configured.length}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Baselines Configured</p>
          </div>
        </VaultCard>
        <VaultCard className={`flex items-center gap-4 ${missing.length > 0 ? "border-red-500/30" : ""}`}>
          <div className="p-2 rounded-md bg-red-500/10">
            <XCircle size={20} className="text-red-400" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{missing.length}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Missing Baseline</p>
          </div>
        </VaultCard>
        <VaultCard className={`flex items-center gap-4 ${totalExceptions > 0 ? "border-amber-500/20" : ""}`}>
          <div className="p-2 rounded-md bg-amber-500/10">
            <AlertTriangle size={20} className="text-amber-400" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{totalExceptions}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Active / Pending Exceptions</p>
          </div>
        </VaultCard>
      </div>

      {orgBaseline && (
        <>
          <h2 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-3">Org Policy Layer</h2>
          <OrgBaselineCard orgBaseline={orgBaseline} inheritingCount={inheritingCount} />
        </>
      )}

      <h2 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-3 mt-6">Project Baselines</h2>
      {isLoading ? (
        <p className="text-bone-muted font-mono text-sm">Loading policy records...</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {baselines?.map((p) => (
            <BaselineCard
              key={p.project_id}
              p={p}
              orgBaseline={orgBaseline}
              onExceptionClick={(id) => navigate(`/exceptions/${id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
