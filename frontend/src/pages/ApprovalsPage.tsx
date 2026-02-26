import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePendingApprovals } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatRelativeTime, ageColor } from "@/lib/utils";
import type { ApprovalRequest, ApprovalStatus } from "@/lib/types";

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

export function ApprovalsPage() {
  const { data: approvals, isLoading } = usePendingApprovals();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabKey>("all");

  const filtered = filterByTab(approvals ?? [], activeTab);

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Pending Clearances</h1>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-slate-border">
        {TABS.map((tab) => {
          const count = filterByTab(approvals ?? [], tab.key).length;
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

      {isLoading ? (
        <p className="text-bone-muted font-mono text-sm">Scanning clearance queue...</p>
      ) : !filtered.length ? (
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
        </div>
      )}
    </div>
  );
}
