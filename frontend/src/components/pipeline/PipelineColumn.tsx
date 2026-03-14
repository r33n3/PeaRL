import { ChevronDown } from "lucide-react";
import { ProjectPipelineCard } from "./ProjectPipelineCard";
import type { Environment, ProjectSummary } from "@/lib/types";

interface Props {
  env: Environment;
  label: string;
  projects: ProjectSummary[];
  onHeaderClick: () => void;
}

export function PipelineColumn({ env, label, projects, onHeaderClick }: Props) {
  return (
    <div className="w-52 flex-shrink-0 flex flex-col">
      <button
        onClick={onHeaderClick}
        className="flex items-center gap-2 px-3 py-2 mb-3 rounded-md border border-slate-border hover:border-cold-teal/30 hover:bg-cold-teal/5 transition-all duration-150 text-left w-full"
      >
        <span className={`env-${env}`}>{label}</span>
        <ChevronDown size={12} className="text-bone-muted ml-auto flex-shrink-0" />
      </button>
      <div className="flex flex-col gap-2">
        {projects.length === 0 ? (
          <p className="text-bone-dim font-mono text-[10px] px-3 py-6 text-center">
            No projects
          </p>
        ) : (
          projects.map((p) => (
            <ProjectPipelineCard key={p.project_id} project={p} />
          ))
        )}
      </div>
    </div>
  );
}
