import { Shield, Wrench, ArrowUp, Search, FileText, AlertCircle } from "lucide-react";
import { MonoText } from "./MonoText";
import { VaultCard } from "./VaultCard";
import { formatTimestamp } from "@/lib/utils";
import type { TimelineEvent } from "@/lib/types";

function eventIcon(eventType: string) {
  if (eventType === "finding_detected") return <Search size={14} className="text-dried-blood-bright" />;
  if (eventType === "finding_resolved") return <Shield size={14} className="text-cold-teal" />;
  if (eventType === "agent_claimed") return <FileText size={14} className="text-clinical-cyan" />;
  if (eventType === "agent_fixed") return <Wrench size={14} className="text-cold-teal" />;
  if (eventType === "gate_evaluated") return <Shield size={14} className="text-clinical-cyan" />;
  if (eventType === "elevated") return <ArrowUp size={14} className="text-cold-teal" />;
  return <AlertCircle size={14} className="text-bone-dim" />;
}

function eventColor(eventType: string): string {
  if (eventType === "finding_detected") return "border-l-dried-blood-bright/50";
  if (eventType === "agent_fixed" || eventType === "elevated" || eventType === "finding_resolved")
    return "border-l-cold-teal/50";
  if (eventType === "gate_evaluated" || eventType === "agent_claimed")
    return "border-l-clinical-cyan/30";
  return "border-l-slate-border";
}

interface TimelinePanelProps {
  events: TimelineEvent[];
  isLoading?: boolean;
  maxItems?: number;
}

export function TimelinePanel({ events, isLoading, maxItems = 20 }: TimelinePanelProps) {
  if (isLoading) {
    return (
      <VaultCard>
        <p className="text-xs font-mono text-bone-dim animate-pulse">Loading timeline...</p>
      </VaultCard>
    );
  }

  const displayed = events.slice(0, maxItems);

  return (
    <div className="space-y-0">
      {displayed.length === 0 && (
        <p className="text-xs font-mono text-bone-dim px-2 py-3">No timeline events yet.</p>
      )}
      {displayed.map((ev) => (
        <div
          key={ev.event_id}
          className={`flex gap-3 border-l-2 pl-3 py-2 ${eventColor(ev.event_type)} hover:bg-wet-stone/30 transition-colors`}
        >
          <div className="mt-0.5 flex-shrink-0">{eventIcon(ev.event_type)}</div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-mono text-bone leading-snug truncate">{ev.summary}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <MonoText className="text-[10px] text-bone-dim">{formatTimestamp(ev.timestamp)}</MonoText>
              <span className="text-[10px] font-mono text-bone-dim opacity-60">·</span>
              <span className="text-[10px] font-mono text-bone-dim">{ev.actor}</span>
              {ev.task_packet_id && (
                <>
                  <span className="text-[10px] font-mono text-bone-dim opacity-60">·</span>
                  <MonoText className="text-[10px] text-clinical-cyan">{ev.task_packet_id}</MonoText>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
