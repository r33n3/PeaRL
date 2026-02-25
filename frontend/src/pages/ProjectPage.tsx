import { useParams, useNavigate } from "react-router-dom";
import { useProjectOverview } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { GateProgress } from "@/components/shared/GateProgress";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import { Bug, ArrowUpCircle, FileText, Shield, DollarSign } from "lucide-react";
import type { ApprovalStatus, Environment } from "@/lib/types";

const ENV_ORDER: Environment[] = ["sandbox", "dev", "pilot", "preprod", "prod"];

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { data, isLoading } = useProjectOverview(projectId!);

  if (isLoading || !data) {
    return <p className="text-bone-muted font-mono text-sm">Loading project record...</p>;
  }

  const overview = data as Record<string, any>;
  const currentEnv = overview.environment ?? "dev";

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">{overview.name ?? projectId}</h1>
          <MonoText className="text-xs">{projectId}</MonoText>
        </div>
        <EnvBadge env={currentEnv} />
      </div>

      {/* Promotion pipeline */}
      <div className="flex items-center gap-2 mb-6">
        {ENV_ORDER.map((env, i) => (
          <div key={env} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-mono uppercase border ${
                env === currentEnv
                  ? "bg-cold-teal/20 text-cold-teal border-cold-teal"
                  : ENV_ORDER.indexOf(env) < ENV_ORDER.indexOf(currentEnv as Environment)
                    ? "bg-wet-stone text-bone-muted border-bone-dim"
                    : "border-slate-border text-bone-dim border-dashed"
              }`}
            >
              {env.slice(0, 2)}
            </div>
            {i < ENV_ORDER.length - 1 && (
              <div className={`w-8 h-px ${
                ENV_ORDER.indexOf(env) < ENV_ORDER.indexOf(currentEnv as Environment)
                  ? "bg-bone-dim"
                  : "bg-slate-border"
              }`} />
            )}
          </div>
        ))}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <VaultCard>
          <div className="flex items-center gap-2 mb-2">
            <Bug size={14} className="text-bone-muted" />
            <span className="vault-heading text-xs">Findings</span>
          </div>
          <p className="text-2xl font-heading font-bold text-bone">{overview.total_open_findings ?? 0}</p>
          <div className="flex gap-2 mt-2">
            {Object.entries((overview.findings_by_severity as Record<string, number>) ?? {}).map(([s, c]) => (
              <span key={s} className="text-[10px] font-mono text-bone-muted">
                {s}: {c}
              </span>
            ))}
          </div>
        </VaultCard>

        <VaultCard>
          <div className="flex items-center gap-2 mb-2">
            <Shield size={14} className="text-bone-muted" />
            <span className="vault-heading text-xs">Gate Status</span>
          </div>
          <GateProgress passed={overview.gate_passed ?? 0} total={overview.gate_total ?? 0} />
          <p className="text-xs font-mono text-bone-muted mt-2">
            {overview.gate_status ?? "not evaluated"}
          </p>
        </VaultCard>

        <VaultCard>
          <div className="flex items-center gap-2 mb-2">
            <DollarSign size={14} className="text-bone-muted" />
            <span className="vault-heading text-xs">Cost</span>
          </div>
          <p className="text-2xl font-heading font-bold text-bone font-mono">
            ${(overview.total_cost_usd ?? 0).toFixed(4)}
          </p>
        </VaultCard>
      </div>

      {/* Quick nav */}
      <div className="flex gap-2 mb-8">
        <button className="btn-teal" onClick={() => navigate(`/projects/${projectId}/findings`)}>
          <Bug size={14} /> Findings
        </button>
        <button className="btn-cyan" onClick={() => navigate(`/projects/${projectId}/promotions`)}>
          <ArrowUpCircle size={14} /> Promotions
        </button>
        <button className="btn-ghost" onClick={() => navigate(`/projects/${projectId}/reports`)}>
          <FileText size={14} /> Reports
        </button>
      </div>

      {/* Pending approvals */}
      {(overview.pending_approvals as any[])?.length > 0 && (
        <div className="mb-8">
          <h2 className="vault-heading text-sm mb-3">Pending Clearances</h2>
          <div className="space-y-2">
            {(overview.pending_approvals as any[]).map((a: any) => (
              <VaultCard
                key={a.approval_request_id}
                interactive
                onClick={() => navigate(`/approvals/${a.approval_request_id}`)}
                className="flex items-center justify-between"
              >
                <div>
                  <span className="text-sm text-bone">{a.request_type.replace(/_/g, " ")}</span>
                  <MonoText className="block text-xs">{a.approval_request_id}</MonoText>
                </div>
                <StatusBadge status={a.status as ApprovalStatus} />
              </VaultCard>
            ))}
          </div>
        </div>
      )}

      {/* Activity timeline */}
      <h2 className="vault-heading text-sm mb-3">Recent Activity</h2>
      <div className="space-y-0">
        {(overview.recent_activity as any[])?.map((a: any, i: number) => (
          <div
            key={i}
            className={`flex items-center gap-4 px-4 py-2.5 ${
              i % 2 === 0 ? "bg-charcoal" : "bg-vault-black"
            }`}
          >
            <MonoText className="text-xs w-32 flex-shrink-0">
              {formatTimestamp(a.created_at)}
            </MonoText>
            <span className="text-xs text-bone-muted w-24 flex-shrink-0">{a.actor ?? a.source}</span>
            <span className="text-sm text-bone">{a.action ?? a.event_type}</span>
          </div>
        ))}
        {!(overview.recent_activity as any[])?.length && (
          <p className="text-sm text-bone-dim font-mono px-4 py-4">No recent activity</p>
        )}
      </div>
    </div>
  );
}
