import { X, Shield } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import type { GateData } from "@/api/promotions";
import type { Environment } from "@/lib/types";

interface Props {
  env: Environment | null;
  gates: GateData[];
  onClose: () => void;
}

export function GateDrawer({ env, gates, onClose }: Props) {
  if (!env) return null;

  const relevantGates = gates.filter((g) => g.source_environment === env);

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-vault-black/60"
        onClick={onClose}
      />
      <aside className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-charcoal border-l border-slate-border flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-border">
          <div>
            <h2 className="vault-heading text-sm">Gate Rules</h2>
            <p className="mono-data text-xs mt-0.5 uppercase tracking-wider">
              {env} → next stage
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-bone-muted hover:text-bone transition-colors p-1"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {relevantGates.length === 0 ? (
            <p className="mono-data text-xs text-center py-8">
              No gates configured for this stage.
            </p>
          ) : (
            relevantGates.map((gate) => (
              <VaultCard key={gate.gate_id} className="p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Shield size={12} className="text-cold-teal flex-shrink-0" />
                  <span className="vault-heading text-xs">
                    {gate.source_environment} → {gate.target_environment}
                  </span>
                  <span className="ml-auto text-[9px] font-mono text-bone-dim border border-slate-border rounded px-1.5 py-0.5 uppercase flex-shrink-0">
                    {gate.approval_mode}
                  </span>
                </div>
                <div className="space-y-1.5">
                  {gate.rules.length === 0 ? (
                    <p className="mono-data text-[10px]">No rules defined.</p>
                  ) : (
                    gate.rules.map((rule) => (
                      <div
                        key={rule.rule_id}
                        className="flex items-start gap-2"
                      >
                        <span
                          className={`mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                            rule.required ? "bg-cold-teal" : "bg-bone-dim"
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-[10px] text-bone-muted uppercase tracking-wide leading-tight">
                            {rule.rule_type.replace(/_/g, " ")}
                          </p>
                          {rule.threshold != null && (
                            <p className="text-[10px] text-bone-dim font-mono">
                              threshold: {rule.threshold}
                            </p>
                          )}
                        </div>
                        {rule.required && (
                          <span className="ml-auto text-[9px] font-mono text-cold-teal flex-shrink-0">
                            req
                          </span>
                        )}
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
