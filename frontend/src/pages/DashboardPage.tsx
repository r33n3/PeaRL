import { useNavigate } from "react-router-dom";
import { useProjects } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { GateProgress } from "@/components/shared/GateProgress";
import { MonoText } from "@/components/shared/MonoText";
import { Shield, AlertTriangle } from "lucide-react";

export function DashboardPage() {
  const { data: projects, isLoading } = useProjects();
  const navigate = useNavigate();

  const totalPending = projects?.reduce((s, p) => s + p.pending_approvals, 0) ?? 0;
  const totalFindings = projects?.reduce((s, p) => s + p.total_open_findings, 0) ?? 0;

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Projects</h1>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <VaultCard className="flex items-center gap-4">
          <div className="p-2 rounded-md bg-cold-teal/10">
            <Shield size={20} className="text-cold-teal" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{projects?.length ?? 0}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Projects</p>
          </div>
        </VaultCard>
        <VaultCard className="flex items-center gap-4">
          <div className="p-2 rounded-md bg-clinical-cyan/10">
            <AlertTriangle size={20} className="text-clinical-cyan" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{totalPending}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Pending Clearances</p>
          </div>
        </VaultCard>
        <VaultCard className="flex items-center gap-4">
          <div className="p-2 rounded-md bg-dried-blood/10">
            <AlertTriangle size={20} className="text-dried-blood-bright" />
          </div>
          <div>
            <p className="text-2xl font-heading font-bold text-bone">{totalFindings}</p>
            <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">Open Findings</p>
          </div>
        </VaultCard>
      </div>

      {/* Project grid */}
      {isLoading ? (
        <p className="text-bone-muted font-mono text-sm">Loading archive records...</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects?.map((p, i) => (
            <VaultCard
              key={p.project_id}
              interactive
              onClick={() => navigate(`/projects/${p.project_id}`)}
              className="stagger-item"
              style={{ animationDelay: `${i * 50}ms` } as React.CSSProperties}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-heading font-semibold text-bone text-lg">{p.name}</h3>
                  <MonoText className="text-xs">{p.project_id}</MonoText>
                </div>
                {p.environment && <EnvBadge env={p.environment} />}
              </div>

              <GateProgress
                passed={Math.round((p.gate_progress_pct / 100) * 20)}
                total={20}
                className="mb-3"
              />

              <div className="flex items-center justify-between text-xs">
                <div className="flex gap-3">
                  {Object.entries(p.findings_by_severity).map(([sev, count]) => (
                    <span key={sev} className="flex items-center gap-1">
                      <span className={`w-2 h-2 rounded-full ${
                        sev === "critical" ? "bg-dried-blood-bright" :
                        sev === "high" ? "bg-orange-400" :
                        "bg-bone-dim"
                      }`} />
                      <MonoText>{count}</MonoText>
                    </span>
                  ))}
                </div>
                {p.pending_approvals > 0 && (
                  <span className="badge-pending text-[10px]">
                    {p.pending_approvals} pending
                  </span>
                )}
              </div>
            </VaultCard>
          ))}
        </div>
      )}

      {/* Governance queue */}
      {(() => {
        const projectsWithPending = (projects ?? []).filter((p) => (p.pending_approvals ?? 0) > 0);
        if (projectsWithPending.length === 0) return null;
        return (
          <div className="mt-8">
            <h2 className="vault-heading text-lg mb-4 flex items-center gap-2">
              <span>Governance Queue</span>
              <span className="ml-2 px-2 py-0.5 rounded bg-clinical-cyan/20 text-clinical-cyan text-xs font-mono">
                {projectsWithPending.reduce((sum, p) => sum + (p.pending_approvals ?? 0), 0)} pending
              </span>
            </h2>
            <div className="space-y-2">
              {projectsWithPending.map((p) => (
                <div
                  key={p.project_id}
                  className="flex items-center justify-between px-4 py-3 rounded border border-clinical-cyan/30 bg-clinical-cyan/5 cursor-pointer hover:border-clinical-cyan transition-colors"
                  onClick={() => navigate(`/projects/${p.project_id}`)}
                >
                  <div>
                    <p className="text-sm font-heading font-semibold text-bone">{p.name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] font-mono text-bone-dim">{p.project_id}</span>
                      {p.target_id && (
                        <span className="text-[10px] font-mono text-bone-dim">
                          → {p.target_type ? `${p.target_type}:` : ""}{p.target_id}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {p.environment && <EnvBadge env={p.environment} />}
                    <span className="text-xs font-mono text-clinical-cyan">
                      {p.pending_approvals} pending
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
