import { useState } from "react";
import { useProjects, usePortfolioMetrics } from "@/api/dashboard";
import { useGates } from "@/api/promotions";
import { useDefaultPipeline } from "@/api/pipelines";
import { PipelineColumn } from "@/components/pipeline/PipelineColumn";
import { GateConnector } from "@/components/pipeline/GateConnector";
import { GateDrawer } from "@/components/pipeline/GateDrawer";
import { MetricsBar } from "@/components/pipeline/MetricsBar";
import type { ProjectSummary } from "@/lib/types";

export function PipelineDashboardPage() {
  const { data: projects = [] } = useProjects();
  const { data: gates = [] } = useGates();
  const { data: metrics } = usePortfolioMetrics();
  const { data: pipeline } = useDefaultPipeline();
  const [activeGateEnv, setActiveGateEnv] = useState<string | null>(null);

  const stages = pipeline ? [...pipeline.stages].sort((a, b) => a.order - b.order) : [];

  const projectsByEnv: Record<string, ProjectSummary[]> = {};
  for (const s of stages) projectsByEnv[s.key] = [];
  for (const p of projects) {
    const env = p.environment ?? "";
    if (env in projectsByEnv) projectsByEnv[env].push(p);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="px-6 py-4 border-b border-slate-border flex-shrink-0">
        <h1 className="vault-heading text-lg">Pipeline Overview</h1>
        <p className="mono-data text-xs mt-0.5">
          {projects.length} project{projects.length !== 1 ? "s" : ""} across{" "}
          {stages.length} environments
        </p>
      </div>

      {/* Pipeline columns — horizontally scrollable */}
      <div className="flex-1 overflow-auto">
        <div className="flex min-w-max h-full p-6 gap-0">
          {stages.map((stage, idx) => (
            <div key={stage.key} className="flex items-start">
              <PipelineColumn
                env={stage.key}
                label={stage.label.toUpperCase()}
                projects={projectsByEnv[stage.key] ?? []}
                onHeaderClick={() => setActiveGateEnv(stage.key)}
              />
              {idx < stages.length - 1 && (
                <GateConnector
                  sourceEnv={stage.key}
                  targetEnv={stages[idx + 1]!.key}
                  gates={gates}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Metrics strip */}
      {metrics && <MetricsBar metrics={metrics} />}

      {/* Gate drawer */}
      <GateDrawer
        env={activeGateEnv}
        gates={gates}
        onClose={() => setActiveGateEnv(null)}
      />
    </div>
  );
}
