import { GitCommit, Wrench, CheckCircle } from "lucide-react";
import { MonoText } from "./MonoText";
import { VaultCard } from "./VaultCard";
import type { AgentTaskPacket } from "@/lib/types";

interface AgentRemediationCardProps {
  packet: AgentTaskPacket;
  fixSummary?: string;
  commitRef?: string;
  filesChanged?: string[];
  severity?: string;
  findingTitle?: string;
  gateVerified?: boolean;
}

export function AgentRemediationCard({
  packet,
  fixSummary,
  commitRef,
  filesChanged,
  severity,
  findingTitle,
  gateVerified = false,
}: AgentRemediationCardProps) {
  return (
    <VaultCard className="border border-slate-border/60">
      <div className="grid grid-cols-3 gap-3 divide-x divide-slate-border/40">
        {/* Before — what was found */}
        <div className="pr-3">
          <p className="text-[10px] font-heading uppercase tracking-wider text-bone-dim mb-1.5">
            Finding
          </p>
          {severity && (
            <span className={`inline-block text-[10px] font-mono px-1.5 py-0.5 rounded mb-1 ${
              severity === "critical" ? "bg-dried-blood-bright/20 text-dried-blood-bright" :
              severity === "high" ? "bg-orange-900/20 text-orange-400" :
              "bg-slate-700/30 text-bone-dim"
            }`}>
              {severity.toUpperCase()}
            </span>
          )}
          <p className="text-xs font-mono text-bone leading-snug">
            {findingTitle || (packet.rule_type || "gate rule").replace(/_/g, " ")}
          </p>
          {packet.fix_guidance && (
            <p className="text-[10px] font-mono text-bone-dim mt-1 leading-snug">
              {packet.fix_guidance.slice(0, 100)}{packet.fix_guidance.length > 100 ? "…" : ""}
            </p>
          )}
        </div>

        {/* Action — what the agent did */}
        <div className="px-3">
          <p className="text-[10px] font-heading uppercase tracking-wider text-bone-dim mb-1.5 flex items-center gap-1">
            <Wrench size={10} /> Agent Fix
          </p>
          {fixSummary ? (
            <p className="text-xs font-mono text-bone leading-snug">{fixSummary}</p>
          ) : (
            <p className="text-xs font-mono text-bone-dim italic">
              {packet.status === "in_progress" ? "In progress…" : "Pending"}
            </p>
          )}
          {commitRef && (
            <div className="flex items-center gap-1 mt-1">
              <GitCommit size={10} className="text-clinical-cyan" />
              <MonoText className="text-[10px] text-clinical-cyan">{commitRef.slice(0, 8)}</MonoText>
            </div>
          )}
          {filesChanged && filesChanged.length > 0 && (
            <p className="text-[10px] font-mono text-bone-dim mt-1">
              {filesChanged.length} file{filesChanged.length > 1 ? "s" : ""} changed
            </p>
          )}
        </div>

        {/* After — PeaRL verification */}
        <div className="pl-3">
          <p className="text-[10px] font-heading uppercase tracking-wider text-bone-dim mb-1.5 flex items-center gap-1">
            <CheckCircle size={10} /> PeaRL Verified
          </p>
          {gateVerified ? (
            <div className="flex items-center gap-1.5">
              <CheckCircle size={14} className="text-cold-teal" />
              <span className="text-xs font-mono text-cold-teal">Gate passed</span>
            </div>
          ) : (
            <p className="text-xs font-mono text-bone-dim">
              {packet.status === "in_progress" ? "Awaiting completion" : "Pending re-scan"}
            </p>
          )}
        </div>
      </div>
    </VaultCard>
  );
}
