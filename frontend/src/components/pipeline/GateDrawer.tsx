import { useState, useEffect } from "react";
import { X, Shield, BookOpen, SlidersHorizontal, Save, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import { useOrgBaseline, useSaveOrgBaseline } from "@/api/dashboard";
import type { GateData } from "@/api/promotions";

interface Props {
  env: string | null;
  gates: GateData[];
  onClose: () => void;
}

type OverrideMap = Record<string, Record<string, boolean | undefined>>;

export function GateDrawer({ env, gates, onClose }: Props) {
  const { data: baseline } = useOrgBaseline();
  const saveBaseline = useSaveOrgBaseline();

  // Local override state: category → control → true/false/undefined (undefined = inherit)
  const [overrides, setOverrides] = useState<OverrideMap>({});
  const [isDirty, setIsDirty] = useState(false);
  const [showOverrides, setShowOverrides] = useState(false);

  // Initialise overrides from baseline when env or baseline changes
  useEffect(() => {
    if (!env || !baseline) return;
    const stored = (baseline.environment_defaults as Record<string, unknown> | null)
      ?.gate_overrides as Record<string, OverrideMap> | undefined;
    setOverrides(stored?.[env] ?? {});
    setIsDirty(false);
  }, [env, baseline]);

  if (!env) return null;

  const relevantGates = gates.filter((g) => g.source_environment === env);

  // All enabled org baseline controls grouped by category
  const baselineByCategory: Record<string, string[]> = {};
  if (baseline?.defaults) {
    for (const [category, controls] of Object.entries(baseline.defaults)) {
      const enabled = Object.entries(controls as Record<string, boolean>)
        .filter(([, v]) => v)
        .map(([k]) => k);
      if (enabled.length) baselineByCategory[category] = enabled;
    }
  }
  const totalBaselineControls = Object.values(baselineByCategory).reduce((n, arr) => n + arr.length, 0);

  // All categories from baseline (for overrides panel)
  const allCategories = Object.keys(baseline?.defaults ?? {});

  const getEffective = (category: string, control: string): boolean => {
    const override = overrides[category]?.[control];
    if (override !== undefined) return override;
    return !!((baseline?.defaults as Record<string, Record<string, boolean>> | undefined)?.[category]?.[control]);
  };

  const toggleOverride = (category: string, control: string) => {
    const orgDefault = !!((baseline?.defaults as Record<string, Record<string, boolean>> | undefined)?.[category]?.[control]);
    const current = overrides[category]?.[control];
    setOverrides((prev) => {
      const cat = { ...(prev[category] ?? {}) };
      if (current === undefined) {
        // No override yet → flip from org default
        cat[control] = !orgDefault;
      } else if (current !== orgDefault) {
        // Override differs from org → clear override (inherit)
        delete cat[control];
      } else {
        // Override same as org (shouldn't happen but handle) → flip
        cat[control] = !current;
      }
      return { ...prev, [category]: cat };
    });
    setIsDirty(true);
  };

  const handleSave = () => {
    if (!baseline || !env) return;
    const existingEnvDefaults = (baseline.environment_defaults as Record<string, unknown>) ?? {};
    const existingGateOverrides = (existingEnvDefaults.gate_overrides as Record<string, OverrideMap>) ?? {};
    // Strip undefined values before saving
    const cleanedOverrides: OverrideMap = {};
    for (const [cat, controls] of Object.entries(overrides)) {
      const clean: Record<string, boolean> = {};
      for (const [ctrl, val] of Object.entries(controls)) {
        if (val !== undefined) clean[ctrl] = val;
      }
      if (Object.keys(clean).length) cleanedOverrides[cat] = clean;
    }
    saveBaseline.mutate({
      ...baseline,
      environment_defaults: {
        ...existingEnvDefaults,
        gate_overrides: { ...existingGateOverrides, [env]: cleanedOverrides },
      },
    }, { onSuccess: () => setIsDirty(false) });
  };

  // Count active overrides (controls that differ from org default)
  const overrideCount = Object.entries(overrides).reduce((n, [cat, controls]) => {
    return n + Object.entries(controls).filter(([ctrl, val]) => {
      const orgDefault = !!((baseline?.defaults as Record<string, Record<string, boolean>> | undefined)?.[cat]?.[ctrl]);
      return val !== undefined && val !== orgDefault;
    }).length;
  }, 0);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-vault-black/60" onClick={onClose} />
      <aside className="fixed right-0 top-0 bottom-0 z-50 w-96 bg-charcoal border-l border-slate-border flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-border">
          <div>
            <h2 className="vault-heading text-sm">Gate Rules</h2>
            <p className="mono-data text-xs mt-0.5 uppercase tracking-wider">{env} → next stage</p>
          </div>
          <button onClick={onClose} className="text-bone-muted hover:text-bone transition-colors p-1">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Org Baseline */}
          {totalBaselineControls > 0 && (
            <VaultCard className="border-clinical-cyan/20">
              <div className="flex items-center gap-2 mb-2">
                <BookOpen size={12} className="text-clinical-cyan flex-shrink-0" />
                <span className="vault-heading text-xs text-clinical-cyan">Org Baseline</span>
                <span className="ml-auto text-[9px] font-mono text-bone-dim">{totalBaselineControls} controls</span>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {Object.entries(baselineByCategory).map(([category, controls]) => (
                  <div key={category}>
                    <p className="text-[9px] font-mono text-bone-dim uppercase tracking-wider mb-1">{category.replace(/_/g, " ")}</p>
                    <div className="space-y-0.5 pl-2">
                      {controls.map((control) => {
                        const override = overrides[category]?.[control];
                        const isRelaxed = override === false;
                        return (
                          <div key={control} className="flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isRelaxed ? "bg-dried-blood-bright/60" : "bg-clinical-cyan/60"}`} />
                            <span className={`text-[10px] font-mono truncate ${isRelaxed ? "text-bone-dim line-through" : "text-bone-muted"}`}>
                              {control.replace(/_/g, " ")}
                            </span>
                            {isRelaxed && <span className="text-[9px] font-mono text-dried-blood-bright ml-auto flex-shrink-0">relaxed</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </VaultCard>
          )}

          {/* Gate Overrides */}
          <VaultCard className={`border-cold-teal/20 ${showOverrides ? "" : ""}`}>
            <button
              className="flex items-center gap-2 w-full"
              onClick={() => setShowOverrides((v) => !v)}
            >
              <SlidersHorizontal size={12} className="text-cold-teal flex-shrink-0" />
              <span className="vault-heading text-xs text-cold-teal">Gate Overrides</span>
              {overrideCount > 0 && (
                <span className="text-[9px] font-mono text-cold-teal bg-cold-teal/10 px-1.5 py-0.5 rounded">
                  {overrideCount} active
                </span>
              )}
              <span className="ml-auto">
                {showOverrides ? <ChevronDown size={12} className="text-bone-muted" /> : <ChevronRight size={12} className="text-bone-muted" />}
              </span>
            </button>
            {!showOverrides && (
              <p className="text-[10px] font-mono text-bone-dim mt-1">
                Override baseline controls for the {env} → next stage gate
              </p>
            )}

            {showOverrides && (
              <div className="mt-3 space-y-3 max-h-72 overflow-y-auto">
                {allCategories.map((category) => {
                  const allControls = Object.keys(
                    (baseline?.defaults as Record<string, Record<string, boolean>> | undefined)?.[category] ?? {}
                  );
                  return (
                    <div key={category}>
                      <p className="text-[9px] font-mono text-bone-dim uppercase tracking-wider mb-1.5">
                        {category.replace(/_/g, " ")}
                      </p>
                      <div className="space-y-1 pl-1">
                        {allControls.map((control) => {
                          const effective = getEffective(category, control);
                          const hasOverride = overrides[category]?.[control] !== undefined;
                          const orgDefault = !!((baseline?.defaults as Record<string, Record<string, boolean>> | undefined)?.[category]?.[control]);
                          return (
                            <label key={control} className="flex items-center gap-2 cursor-pointer group">
                              <input
                                type="checkbox"
                                checked={effective}
                                onChange={() => toggleOverride(category, control)}
                                className="accent-cold-teal cursor-pointer"
                              />
                              <span className={`text-[10px] font-mono flex-1 truncate ${effective ? "text-bone" : "text-bone-dim"}`}>
                                {control.replace(/_/g, " ")}
                              </span>
                              {hasOverride && effective !== orgDefault && (
                                <span className={`text-[9px] font-mono flex-shrink-0 ${effective ? "text-cold-teal" : "text-dried-blood-bright"}`}>
                                  {effective ? "enforced" : "relaxed"}
                                </span>
                              )}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {isDirty && (
              <div className="mt-3 pt-3 border-t border-slate-border flex justify-end">
                <button
                  className="btn-teal text-xs flex items-center gap-1.5"
                  onClick={handleSave}
                  disabled={saveBaseline.isPending}
                >
                  {saveBaseline.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save Overrides
                </button>
              </div>
            )}
          </VaultCard>

          {/* Gate rules */}
          {relevantGates.length === 0 ? (
            <p className="mono-data text-xs text-center py-4">No gates configured for this stage.</p>
          ) : (
            relevantGates.map((gate) => (
              <VaultCard key={gate.gate_id} className="p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Shield size={12} className="text-cold-teal flex-shrink-0" />
                  <span className="vault-heading text-xs">{gate.source_environment} → {gate.target_environment}</span>
                  <span className="ml-auto text-[9px] font-mono text-bone-dim border border-slate-border rounded px-1.5 py-0.5 uppercase flex-shrink-0">
                    {gate.approval_mode}
                  </span>
                </div>
                <div className="space-y-1.5">
                  {gate.rules.length === 0 ? (
                    <p className="mono-data text-[10px]">No explicit rules — baseline applies.</p>
                  ) : (
                    gate.rules.map((rule) => (
                      <div key={rule.rule_id} className="flex items-start gap-2">
                        <span className={`mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0 ${rule.required ? "bg-cold-teal" : "bg-bone-dim"}`} />
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-[10px] text-bone-muted uppercase tracking-wide leading-tight">
                            {rule.rule_type.replace(/_/g, " ")}
                          </p>
                          {rule.description && rule.description !== rule.rule_type && (
                            <p className="text-[10px] text-bone font-mono mt-0.5 leading-snug">{rule.description}</p>
                          )}
                          {rule.threshold != null && (
                            <p className="text-[10px] text-bone-dim font-mono">threshold: {rule.threshold}</p>
                          )}
                        </div>
                        {rule.required && <span className="ml-auto text-[9px] font-mono text-cold-teal flex-shrink-0">req</span>}
                      </div>
                    ))
                  )}
                </div>
              </VaultCard>
            ))
          )}
        </div>
      </aside>
    </>
  );
}
