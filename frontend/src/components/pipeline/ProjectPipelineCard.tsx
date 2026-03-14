import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import type { ProjectSummary } from "@/lib/types";

interface Props {
  project: ProjectSummary;
}

function statusDot(gateStatus: string | null) {
  if (gateStatus === "passed") return "bg-cold-teal";
  if (gateStatus === "failed") return "bg-dried-blood-bright";
  if (gateStatus === "partial") return "bg-yellow-500";
  return "bg-bone-dim";
}

function statusLabel(gateStatus: string | null) {
  if (gateStatus === "passed") return "passing";
  if (gateStatus === "failed") return "blocked";
  if (gateStatus === "partial") return "partial";
  return "not evaluated";
}

export function ProjectPipelineCard({ project }: Props) {
  const navigate = useNavigate();

  return (
    <VaultCard
      interactive
      onClick={() => navigate(`/projects/${project.project_id}`)}
      className="p-3"
    >
      <div className="flex items-start gap-2">
        <span
          className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${statusDot(project.gate_status)}`}
        />
        <div className="min-w-0 flex-1">
          <p className="text-bone text-xs font-heading font-semibold truncate">
            {project.name}
          </p>
          <p className="mono-data text-[10px] mt-0.5">
            {statusLabel(project.gate_status)}
          </p>
          <p className="mono-data text-[10px] mt-1">
            {project.total_open_findings} finding
            {project.total_open_findings !== 1 ? "s" : ""}
          </p>
          {project.pending_approvals > 0 && (
            <span className="inline-flex items-center gap-0.5 mt-1 px-1.5 py-0.5 rounded bg-cold-teal/10 text-cold-teal text-[9px] font-mono animate-pulse">
              <AlertTriangle size={9} />
              {project.pending_approvals} pending
            </span>
          )}
        </div>
      </div>
    </VaultCard>
  );
}
