import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePendingApprovals } from "@/api/dashboard";
import { usePendingExceptions } from "@/api/approvals";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatRelativeTime, ageColor } from "@/lib/utils";
import type { ApprovalRequest, ApprovalStatus, PendingException } from "@/lib/types";

type TabKey = "all" | "promotions" | "exceptions" | "other";

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "promotions", label: "Promotions" },
  { key: "exceptions", label: "Exceptions" },
  { key: "other", label: "Other" },
];

function filterByTab(approvals: ApprovalRequest[], tab: TabKey): ApprovalRequest[] {
  if (tab === "all") return approvals;
  if (tab === "promotions") return approvals.filter((a) => a.request_type === "promotion_gate");
  if (tab === "exceptions") return approvals.filter((a) => a.request_type === "exception");
  return approvals.filter(
    (a) => a.request_type !== "promotion_gate" && a.request_type !== "exception"
  );
}

const CONTEST_TYPE_LABELS: Record<string, string> = {
  false_positive: "False Positive",
  risk_acceptance: "Risk Acceptance",
  needs_more_time: "Needs More Time",
};

function ExceptionRecordCard({ exc, index }: { exc: PendingException; index: number }) {
  const navigate = useNavigate();
  const controls = exc.compensating_controls ?? [];
  return (
    <VaultCard
      interactive
      onClick={() => navigate(`/exceptions/${exc.exception_id}`)}
      className="stagger-item flex items-center justify-between"
      style={{ animationDelay: `${index * 50}ms` } as React.CSSProperties}
    >
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-1 flex-wrap">
          <span className="text-sm font-heading font-semibold text-bone uppercase">Exception</span>
          <StatusBadge status={exc.status as ApprovalStatus} />
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cold-teal/10 text-cold-teal border border-cold-teal/20">
            Direct
          </span>
        </div>
        <div className="flex items-center gap-4">
          <MonoText className="text-xs">{exc.project_id}</MonoText>
          <span className="text-xs text-bone-dim font-mono truncate max-w-xs">{exc.rationale}</span>
        </div>
        {controls.length > 0 && (
          <p className="text-[10px] font-mono text-bone-dim mt-0.5">
            {controls.length} compensating control{controls.length !== 1 ? "s" : ""}
          </p>
        )}
      </div>
      <div className="text-right">
        <MonoText className={`text-xs ${ageColor(exc.created_at)}`}>
          {formatRelativeTime(exc.created_at)}
        </MonoText>
        <MonoText className="block text-[10px]">{exc.exception_id}</MonoText>
      </div>
    </VaultCard>
  );
}

export function ApprovalsPage() {
  const { data: approvals, isLoading } = usePendingApprovals();
  const { data: pendingExceptions, isLoading: excLoading } = usePendingExceptions();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabKey>("all");

  const approvalList = approvals ?? [];
  const excList = pendingExceptions ?? [];
  const filtered = filterByTab(approvalList, activeTab);
  const showExceptions = activeTab === "exceptions" || activeTab === "all";

  // Tab counts: exceptions tab includes both approval-request exceptions AND direct exceptions
  const tabCount = (tab: TabKey): number => {
    const approvalCount = filterByTab(approvalList, tab).length;
    if (tab === "exceptions") return approvalCount + excList.length;
    if (tab === "all") return approvalList.length + excList.length;
    return approvalCount;
  };

  const loading = isLoading || excLoading;

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Pending Clearances</h1>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-slate-border">
        {TABS.map((tab) => {
          const count = tabCount(tab.key);
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-2 text-xs font-heading uppercase tracking-wider border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-clinical-cyan text-clinical-cyan"
                  : "border-transparent text-bone-dim hover:text-bone-muted"
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span className="ml-1.5 text-[10px] font-mono text-bone-dim">({count})</span>
              )}
            </button>
          );
        })}
      </div>

      {loading ? (
        <p className="text-bone-muted font-mono text-sm">Scanning clearance queue...</p>
      ) : !filtered.length && !(showExceptions && excList.length > 0) ? (
        <VaultCard className="text-center py-12">
          <p className="text-bone-dim font-mono text-sm">No pending clearances</p>
          <p className="text-bone-dim font-mono text-xs mt-1">All records are in order</p>
        </VaultCard>
      ) : (
        <div className="space-y-3">
          {filtered.map((a, i) => {
            const rd = a.request_data as Record<string, unknown> | undefined;
            const isException = a.request_type === "exception";
            return (
              <VaultCard
                key={a.approval_request_id}
                interactive
                onClick={() => navigate(`/approvals/${a.approval_request_id}`)}
                className="stagger-item flex items-center justify-between"
                style={{ animationDelay: `${i * 50}ms` } as React.CSSProperties}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1 flex-wrap">
                    <span className="text-sm font-heading font-semibold text-bone uppercase">
                      {a.request_type.replace(/_/g, " ")}
                    </span>
                    <StatusBadge status={a.status as ApprovalStatus} />
                    {isException && !!rd?.rule_type && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-dried-blood/10 text-dried-blood-bright border border-dried-blood/20">
                        {(rd.rule_type as string).replace(/_/g, " ")}
                      </span>
                    )}
                    {isException && !!rd?.contest_type && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-clinical-cyan/10 text-clinical-cyan">
                        {CONTEST_TYPE_LABELS[rd.contest_type as string] ?? (rd.contest_type as string)}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <MonoText className="text-xs">{a.project_id}</MonoText>
                    <span className="text-xs text-bone-dim">
                      {a.environment}
                    </span>
                  </div>
                </div>

                <div className="text-right">
                  <MonoText className={`text-xs ${ageColor(a.created_at)}`}>
                    {formatRelativeTime(a.created_at)}
                  </MonoText>
                  <MonoText className="block text-[10px]">{a.approval_request_id}</MonoText>
                </div>
              </VaultCard>
            );
          })}

          {/* Direct exceptions (no linked approval request) */}
          {showExceptions && excList.map((exc, i) => (
            <ExceptionRecordCard key={exc.exception_id} exc={exc} index={filtered.length + i} />
          ))}
        </div>
      )}
    </div>
  );
}
