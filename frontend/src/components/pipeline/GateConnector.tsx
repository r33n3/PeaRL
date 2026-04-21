import { Shield } from "lucide-react";
import type { GateData } from "@/api/promotions";

interface Props {
  sourceEnv: string;
  targetEnv: string;
  gates: GateData[];
}

export function GateConnector({ sourceEnv, targetEnv, gates }: Props) {
  const gate = gates.find(
    (g) => g.source_environment === sourceEnv && g.target_environment === targetEnv
  );

  return (
    <div className="flex items-start pt-9 px-1 w-20 flex-shrink-0">
      <div className="flex flex-col items-center w-full gap-1.5">
        <div className="w-full flex items-center relative">
          <div className="w-full h-px bg-slate-border" />
          <div className="absolute left-1/2 -translate-x-1/2 bg-charcoal px-1.5 py-1 rounded border border-slate-border flex items-center gap-1 whitespace-nowrap">
            <Shield size={10} className="text-cold-teal/70 flex-shrink-0" />
            {gate ? (
              <>
                <span className="text-[9px] font-mono text-bone-muted">
                  {gate.rule_count}
                </span>
                <span className="text-[9px] font-mono text-bone-dim">
                  {gate.approval_mode === "manual" ? "M" : "A"}
                </span>
              </>
            ) : (
              <span className="text-[9px] font-mono text-bone-dim">—</span>
            )}
          </div>
        </div>
        <span className="text-[8px] font-mono text-bone-dim opacity-50">
          {sourceEnv[0]}→{targetEnv[0]}
        </span>
      </div>
    </div>
  );
}
