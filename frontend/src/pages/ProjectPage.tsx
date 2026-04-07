import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useProjectOverview, useProjectGovernance } from "@/api/dashboard";
import { useAgentBrief, usePackageIntegrity } from "@/api/agent";
import { useProjectTimeline } from "@/api/timeline";
import { useProjectExceptions, useDecideException, useRevokeException } from "@/api/approvals";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { GateProgress } from "@/components/shared/GateProgress";
import { MonoText } from "@/components/shared/MonoText";
import { TimelinePanel } from "@/components/shared/TimelinePanel";
import { GuardrailsTab } from "@/components/pipeline/GuardrailsTab";
import { SetupTab } from "@/components/pipeline/SetupTab";
import { Bug, ArrowUpCircle, FileText, Shield, DollarSign, Cpu, CheckCircle, Package, AlertTriangle, XCircle, Clock, ShieldCheck, Tag } from "lucide-react";
import type { ApprovalStatus, Environment } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

const ENV_ORDER: Environment[] = ["sandbox", "dev", "preprod", "prod"];

function fmtDays(d: number | null | undefined): string {
  if (d == null) return "—";
  if (d < 1) return `${Math.round(d * 24)}h`;
  return `${d.toFixed(1)}d`;
}

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"overview" | "guardrails" | "setup">("overview");
  const { data, isLoading } = useProjectOverview(projectId!);
  const { data: agentBrief } = useAgentBrief(projectId);
  const { data: pkgIntegrity } = usePackageIntegrity(projectId);
  const { data: timeline = [], isLoading: timelineLoading } = useProjectTimeline(projectId);
  const { data: gov } = useProjectGovernance(projectId!);
  const { data: exceptions = [] } = useProjectExceptions(projectId);
  const decideExceptionMut = useDecideException();
  const revokeExceptionMut = useRevokeException();

  if (isLoading || !data) {
    return <p className="text-bone-muted font-mono text-sm">Loading project record...</p>;
  }

  const overview = data as Record<string, any>;
  const currentEnv = overview.environment ?? "sandbox";

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
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
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
            <span className="vault-heading text-xs">PeaRL Cost</span>
          </div>
          <p className="text-2xl font-heading font-bold text-bone font-mono">
            ${(overview.total_cost_usd ?? 0).toFixed(4)}
          </p>
          <p className="text-[10px] font-mono text-bone-dim mt-0.5">
            {overview.cost_window_start
              ? `${formatTimestamp(overview.cost_window_start)} → ${formatTimestamp(overview.cost_window_end ?? null)}`
              : "since registration"}
          </p>
        </VaultCard>

        {/* Agent Status card */}
        <VaultCard className={agentBrief?.ready_to_elevate ? "border-cold-teal/30" : ""}>
          <div className="flex items-center gap-2 mb-2">
            <Cpu size={14} className="text-bone-muted" />
            <span className="vault-heading text-xs">Agent Status</span>
          </div>
          {agentBrief ? (
            <>
              {agentBrief.ready_to_elevate ? (
                <div className="flex items-center gap-1.5">
                  <CheckCircle size={16} className="text-cold-teal" />
                  <span className="text-sm font-mono text-cold-teal font-semibold">Ready</span>
                </div>
              ) : (
                <p className="text-2xl font-heading font-bold text-bone">
                  {agentBrief.blockers_count}
                </p>
              )}
              <p className="text-[10px] font-mono text-bone-dim mt-1">
                {agentBrief.ready_to_elevate
                  ? `${agentBrief.current_stage} → ${agentBrief.next_stage}`
                  : `blocker${agentBrief.blockers_count !== 1 ? "s" : ""}`}
              </p>
            </>
          ) : (
            <p className="text-xs font-mono text-bone-dim">—</p>
          )}
        </VaultCard>

        {/* Context Package card */}
        <VaultCard className={
          pkgIntegrity?.status === "tampered" ? "border-red-500/40" :
          pkgIntegrity?.status === "stale" ? "border-amber-500/30" :
          pkgIntegrity?.status === "current" ? "border-cold-teal/20" : ""
        }>
          <div className="flex items-center gap-2 mb-2">
            <Package size={14} className="text-bone-muted" />
            <span className="vault-heading text-xs">Context Package</span>
          </div>
          {pkgIntegrity && pkgIntegrity.status !== "missing" ? (
            <>
              {pkgIntegrity.status === "current" && (
                <div className="flex items-center gap-1.5">
                  <CheckCircle size={16} className="text-cold-teal" />
                  <span className="text-sm font-mono text-cold-teal font-semibold">Current</span>
                </div>
              )}
              {pkgIntegrity.status === "stale" && (
                <div className="flex items-center gap-1.5">
                  <AlertTriangle size={16} className="text-amber-400" />
                  <span className="text-sm font-mono text-amber-400 font-semibold">Recompile</span>
                </div>
              )}
              {pkgIntegrity.status === "tampered" && (
                <div className="flex items-center gap-1.5">
                  <XCircle size={16} className="text-red-400" />
                  <span className="text-sm font-mono text-red-400 font-semibold">Tampered</span>
                </div>
              )}
              <p className="text-[10px] font-mono text-bone-dim mt-1 truncate" title={
                pkgIntegrity.drift_details.length > 0
                  ? pkgIntegrity.drift_details[0]
                  : pkgIntegrity.days_since_compiled != null
                    ? `${pkgIntegrity.days_since_compiled}d ago`
                    : ""
              }>
                {pkgIntegrity.drift_details.length > 0
                  ? pkgIntegrity.drift_details[0]
                  : pkgIntegrity.days_since_compiled != null
                    ? `Compiled ${pkgIntegrity.days_since_compiled}d ago`
                    : ""}
              </p>
            </>
          ) : (
            <p className="text-xs font-mono text-bone-dim">—</p>
          )}
        </VaultCard>
      </div>

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-white/10 mb-8">
        {(["overview", "guardrails", "setup"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-mono border-b-2 transition-colors capitalize ${
              activeTab === tab
                ? "border-purple-500 text-purple-400"
                : "border-transparent text-white/50 hover:text-white/70"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Guardrails tab */}
      {activeTab === "guardrails" && (
        <GuardrailsTab projectId={projectId} />
      )}

      {/* Setup tab */}
      {activeTab === "setup" && (
        <SetupTab projectId={projectId} />
      )}

      {/* Overview tab content */}
      {activeTab === "overview" && <>

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

      {/* Governance Outcomes */}
      {gov && (
        <div className="mb-8">
          <h2 className="vault-heading text-sm mb-3">Governance Outcomes</h2>
          <div className="grid grid-cols-2 gap-4">
            {/* Card 1 — Finding Resolution */}
            <VaultCard>
              <div className="flex items-center gap-2 mb-2">
                <Bug size={14} className="text-bone-muted" />
                <span className="vault-heading text-xs">Finding Resolution</span>
              </div>
              <p className="text-2xl font-heading font-bold text-bone font-mono">
                {fmtDays(gov.mttr_days)}
              </p>
              <p className="text-[10px] font-mono text-bone-dim">avg to resolve</p>
              <div className="flex items-center justify-between mt-2 text-xs font-mono text-bone-muted">
                <span>{gov.findings_resolved_total} resolved / {gov.findings_resolved_total + gov.findings_open_total} total</span>
                {gov.resolution_rate_pct != null && (
                  <span>{gov.resolution_rate_pct.toFixed(0)}%</span>
                )}
              </div>
              {gov.resolution_rate_pct != null && (
                <div className="mt-1.5 h-1.5 bg-wet-stone rounded-full overflow-hidden">
                  <div
                    className="h-full bg-cold-teal rounded-full"
                    style={{ width: `${gov.resolution_rate_pct}%` }}
                  />
                </div>
              )}
            </VaultCard>

            {/* Card 2 — Exception Decisions */}
            <VaultCard>
              <div className="flex items-center gap-2 mb-2">
                <ShieldCheck size={14} className="text-bone-muted" />
                <span className="vault-heading text-xs">Exception Decisions</span>
              </div>
              <div className="flex items-end gap-4 mb-2">
                <div>
                  <p className="text-2xl font-heading font-bold text-cold-teal font-mono">{gov.exceptions_approved}</p>
                  <p className="text-[10px] font-mono text-bone-dim">approved</p>
                </div>
                <div>
                  <p className="text-2xl font-heading font-bold text-red-400 font-mono">{gov.exceptions_rejected}</p>
                  <p className="text-[10px] font-mono text-bone-dim">rejected</p>
                </div>
                {gov.exceptions_pending > 0 && (
                  <div>
                    <p className="text-2xl font-heading font-bold text-amber-400 font-mono">{gov.exceptions_pending}</p>
                    <p className="text-[10px] font-mono text-bone-dim">pending</p>
                  </div>
                )}
              </div>
              <div className="space-y-1 border-t border-slate-border pt-2">
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-bone-dim">avg to approve</span>
                  <span className="text-cold-teal">{fmtDays(gov.avg_time_to_approve_days)}</span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-bone-dim">avg to reject</span>
                  <span className="text-red-400">{fmtDays(gov.avg_time_to_reject_days)}</span>
                </div>
              </div>
            </VaultCard>

            {/* Card 3 — Gate History */}
            <VaultCard>
              <div className="flex items-center gap-2 mb-2">
                <Shield size={14} className="text-bone-muted" />
                <span className="vault-heading text-xs">Gate History</span>
              </div>
              {gov.gate_attempts_total === 0 ? (
                <p className="text-xs font-mono text-bone-dim">Not yet evaluated</p>
              ) : (
                <>
                  <p className="text-sm font-mono text-bone">
                    {gov.gate_first_pass_attempt != null
                      ? `Passed on attempt ${gov.gate_first_pass_attempt} of ${gov.gate_attempts_total}`
                      : `${gov.gate_attempts_total} attempt${gov.gate_attempts_total !== 1 ? "s" : ""}, not yet passed`}
                  </p>
                  <div className="flex items-center gap-1 mt-2">
                    {(gov.gate_attempts_total <= 5
                      ? gov.gate_attempts_total
                      : 5
                    ) > 0 && (() => {
                      const dots = Math.min(gov.gate_attempts_total, 5);
                      const evals = [
                        ...Array(gov.gate_fail_attempts).fill("fail"),
                        ...Array(gov.gate_pass_attempts).fill("pass"),
                      ].slice(0, dots);
                      return evals.map((s, i) => (
                        <div
                          key={i}
                          className={`w-3 h-3 rounded-full ${s === "pass" ? "bg-cold-teal" : "bg-red-500/70"}`}
                          title={s}
                        />
                      ));
                    })()}
                    {gov.gate_attempts_total > 5 && (
                      <span className="text-[10px] font-mono text-bone-dim">
                        +{gov.gate_attempts_total - 5} more
                      </span>
                    )}
                  </div>
                  {gov.last_gate_status && (
                    <p className="text-[10px] font-mono text-bone-dim mt-1">
                      Last: <span className={gov.last_gate_status === "passed" ? "text-cold-teal" : "text-red-400"}>
                        {gov.last_gate_status}
                      </span>
                    </p>
                  )}
                </>
              )}
            </VaultCard>

            {/* Card 3 — Pipeline Duration */}
            <VaultCard>
              <div className="flex items-center gap-2 mb-2">
                <Clock size={14} className="text-bone-muted" />
                <span className="vault-heading text-xs">Pipeline Duration</span>
              </div>
              <p className="text-2xl font-heading font-bold text-bone font-mono">
                {fmtDays(gov.days_in_pipeline)}
              </p>
              <p className="text-[10px] font-mono text-bone-dim">total in pipeline</p>
              <p className="text-xs font-mono text-bone-muted mt-1">
                {fmtDays(gov.days_in_current_env)} in current env
              </p>
              {gov.time_per_environment.length > 0 && (
                <div className="flex items-center gap-1 mt-2 flex-wrap">
                  {gov.time_per_environment.map((e, i) => (
                    <span key={e.environment} className="flex items-center gap-1">
                      {i > 0 && <span className="text-bone-dim text-[10px]">→</span>}
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                        e.exit_at == null
                          ? "bg-cold-teal/20 text-cold-teal"
                          : "bg-wet-stone text-bone-muted"
                      }`}>
                        {e.environment.slice(0, 2)} {fmtDays(e.days)}
                      </span>
                    </span>
                  ))}
                </div>
              )}
            </VaultCard>

            {/* Card 4 — Assessment Cost */}
            <VaultCard>
              <div className="flex items-center gap-2 mb-2">
                <DollarSign size={14} className="text-bone-muted" />
                <span className="vault-heading text-xs">Assessment Cost</span>
              </div>
              <p className="text-2xl font-heading font-bold text-bone font-mono">
                ${gov.total_cost_usd.toFixed(4)}
              </p>
              <p className="text-[10px] font-mono text-bone-dim mt-0.5">
                {gov.cost_window_start
                  ? `${formatTimestamp(gov.cost_window_start)} → ${formatTimestamp(gov.cost_window_end ?? null)}`
                  : "since registration"}
              </p>
              {gov.gate_decision_latency_days != null && (
                <p className="text-xs font-mono text-bone-muted mt-2">
                  avg gate decision: {fmtDays(gov.gate_decision_latency_days)}
                </p>
              )}
            </VaultCard>
          </div>
        </div>
      )}

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

      {/* Exceptions & Acceptances */}
      {exceptions.length > 0 && (
        <div className="mb-8">
          <h2 className="vault-heading text-sm mb-3">Exceptions &amp; Acceptances</h2>
          <div className="space-y-2">
            {(exceptions as any[]).map((exc: any) => {
              const statusColor =
                exc.status === "active" ? "text-cold-teal" :
                exc.status === "pending" ? "text-amber-400" :
                exc.status === "rejected" || exc.status === "revoked" ? "text-red-400" :
                "text-bone-muted";
              const riskColor =
                exc.risk_rating === "critical" ? "text-red-400" :
                exc.risk_rating === "high" ? "text-orange-400" :
                exc.risk_rating === "moderate" ? "text-amber-400" :
                "text-cold-teal";
              return (
                <VaultCard key={exc.exception_id}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs font-mono uppercase ${statusColor}`}>{exc.status}</span>
                        <span className="text-bone-dim text-xs font-mono">·</span>
                        <span className="text-xs font-mono text-bone-muted">{exc.exception_type ?? "exception"}</span>
                        {exc.risk_rating && (
                          <>
                            <span className="text-bone-dim text-xs font-mono">·</span>
                            <span className={`text-xs font-mono ${riskColor}`}>{exc.risk_rating} risk</span>
                          </>
                        )}
                      </div>
                      <p className="text-sm font-heading text-bone truncate">
                        {exc.title ?? exc.exception_id}
                      </p>
                      <p className="text-xs font-mono text-bone-dim mt-0.5 line-clamp-2">{exc.rationale}</p>
                      {exc.scope?.controls?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {exc.scope.controls.map((c: string) => (
                            <span key={c} className="text-[10px] font-mono px-1.5 py-0.5 bg-wet-stone rounded text-bone-muted">{c}</span>
                          ))}
                        </div>
                      )}
                      {exc.expires_at && (
                        <p className="text-[10px] font-mono text-bone-dim mt-1">
                          Expires: {new Date(exc.expires_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {exc.status === "pending" && (
                        <>
                          <button
                            className="btn-teal text-xs"
                            disabled={decideExceptionMut.isPending}
                            onClick={() => decideExceptionMut.mutate({
                              exceptionId: exc.exception_id,
                              decision: "approve",
                              decidedBy: "reviewer",
                            })}
                          >
                            Approve
                          </button>
                          <button
                            className="btn-danger text-xs"
                            disabled={decideExceptionMut.isPending}
                            onClick={() => decideExceptionMut.mutate({
                              exceptionId: exc.exception_id,
                              decision: "reject",
                              decidedBy: "reviewer",
                            })}
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {exc.status === "active" && (
                        <button
                          className="btn-danger text-xs"
                          disabled={revokeExceptionMut.isPending}
                          onClick={() => revokeExceptionMut.mutate({
                            exceptionId: exc.exception_id,
                            revokedBy: "reviewer",
                          })}
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  </div>
                </VaultCard>
              );
            })}
          </div>
        </div>
      )}

      {/* Tags */}
      {(overview.tags as string[] | null)?.length ? (
        <div className="mb-6 flex items-center gap-2">
          <Tag size={12} className="text-bone-muted" />
          <div className="flex flex-wrap gap-1.5">
            {(overview.tags as string[]).map(t => (
              <span key={t} className="text-[10px] font-mono px-2 py-0.5 bg-wet-stone rounded border border-slate-border/50 text-bone-muted">{t}</span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Timeline */}
      <h2 className="vault-heading text-sm mb-3">Project Timeline</h2>
      <VaultCard className="mb-0">
        <TimelinePanel events={timeline} isLoading={timelineLoading} maxItems={25} />
      </VaultCard>

      </> /* end overview tab */}
    </div>
  );
}
