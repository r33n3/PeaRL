import { useState } from "react";
import { useProjects, usePortfolioMetrics } from "@/api/dashboard";
import { useGates } from "@/api/promotions";
import { PipelineColumn } from "@/components/pipeline/PipelineColumn";
import { GateConnector } from "@/components/pipeline/GateConnector";
import { GateDrawer } from "@/components/pipeline/GateDrawer";
import { MetricsBar } from "@/components/pipeline/MetricsBar";
import type { Environment, ProjectSummary } from "@/lib/types";

const STAGES: Environment[] = ["sandbox", "dev", "preprod", "prod"];
const STAGE_LABELS: Record<Environment, string> = {
  sandbox: "SANDBOX",
  dev: "DEV",
  preprod: "PRE-PROD",
  prod: "PROD",
};

export function PipelineDashboardPage() {
  const { data: projects = [] } = useProjects();
  const { data: gates = [] } = useGates();
  const { data: metrics } = usePortfolioMetrics();
  const [activeGateEnv, setActiveGateEnv] = useState<Environment | null>(null);

  const projectsByEnv: Record<Environment, ProjectSummary[]> = {
    sandbox: [],
    dev: [],
    preprod: [],
    prod: [],
  };
  for (const p of projects) {
    const env = (p.environment ?? "sandbox") as Environment;
    if (env in projectsByEnv) {
      projectsByEnv[env].push(p);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="px-6 py-4 border-b border-slate-border flex-shrink-0">
        <h1 className="vault-heading text-lg">Pipeline Overview</h1>
        <p className="mono-data text-xs mt-0.5">
          {projects.length} project{projects.length !== 1 ? "s" : ""} across{" "}
          {STAGES.length} environments
        </p>
      </div>

      {/* Pipeline columns — horizontally scrollable */}
      <div className="flex-1 overflow-auto">
        <div className="flex min-w-max h-full p-6 gap-0">
          {STAGES.map((env, idx) => (
            <div key={env} className="flex items-start">
              <PipelineColumn
                env={env}
                label={STAGE_LABELS[env]}
                projects={projectsByEnv[env]}
                onHeaderClick={() => setActiveGateEnv(env)}
              />
              {idx < STAGES.length - 1 && (
                <GateConnector
                  sourceEnv={env}
                  targetEnv={STAGES[idx + 1]!}
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
