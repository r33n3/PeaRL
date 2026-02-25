import { useNavigate } from "react-router-dom";
import { usePendingApprovals } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatRelativeTime, ageColor } from "@/lib/utils";
import type { ApprovalStatus } from "@/lib/types";

export function ApprovalsPage() {
  const { data: approvals, isLoading } = usePendingApprovals();
  const navigate = useNavigate();

  return (
    <div>
      <h1 className="vault-heading text-2xl mb-6">Pending Clearances</h1>

      {isLoading ? (
        <p className="text-bone-muted font-mono text-sm">Scanning clearance queue...</p>
      ) : !approvals?.length ? (
        <VaultCard className="text-center py-12">
          <p className="text-bone-dim font-mono text-sm">No pending clearances</p>
          <p className="text-bone-dim font-mono text-xs mt-1">All records are in order</p>
        </VaultCard>
      ) : (
        <div className="space-y-3">
          {approvals.map((a, i) => (
            <VaultCard
              key={a.approval_request_id}
              interactive
              onClick={() => navigate(`/approvals/${a.approval_request_id}`)}
              className="stagger-item flex items-center justify-between"
              style={{ animationDelay: `${i * 50}ms` } as React.CSSProperties}
            >
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-sm font-heading font-semibold text-bone uppercase">
                    {a.request_type.replace(/_/g, " ")}
                  </span>
                  <StatusBadge status={a.status as ApprovalStatus} />
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
          ))}
        </div>
      )}
    </div>
  );
}
