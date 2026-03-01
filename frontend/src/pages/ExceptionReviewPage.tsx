import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useDecideException } from "@/api/approvals";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import { CheckCircle, XCircle } from "lucide-react";
import type { PendingException, ApprovalStatus } from "@/lib/types";

const currentUser = { id: "dashboard-user", role: "security_lead" };

export function ExceptionReviewPage() {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const [confirmReject, setConfirmReject] = useState(false);
  const decideException = useDecideException();

  const { data: exc, isLoading } = useQuery({
    queryKey: ["exception", exceptionId],
    queryFn: () =>
      apiFetch<{ exceptions: PendingException[] }>(
        `/projects/_/exceptions`
      ).catch(() => null),
    enabled: false, // We'll fetch via the pending list or project-scoped endpoint below
  });

  // Fetch by scanning pending list (simplest approach without a GET /exceptions/:id endpoint)
  const { data: pendingList, isLoading: pendingLoading } = useQuery({
    queryKey: ["exceptions", "pending"],
    queryFn: () => apiFetch<PendingException[]>("/exceptions/pending"),
  });

  const exception = pendingList?.find((e) => e.exception_id === exceptionId);

  if (pendingLoading) {
    return <p className="text-bone-muted font-mono text-sm">Loading exception record...</p>;
  }

  if (!exception) {
    return (
      <div>
        <p className="text-bone-muted font-mono text-sm">
          Exception <MonoText className="inline">{exceptionId}</MonoText> not found or no longer pending.
        </p>
        <Link to="/approvals" className="text-clinical-cyan text-xs font-mono hover:underline mt-2 block">
          ← Back to clearance queue
        </Link>
      </div>
    );
  }

  const isPending = exception.status === "pending";
  const compensatingControls = exception.compensating_controls ?? [];

  const handleApprove = () => {
    decideException.mutate({
      exceptionId: exception.exception_id,
      decision: "approve",
      decidedBy: currentUser.id,
      reason: "Approved via dashboard",
    });
  };

  const handleReject = () => {
    if (!confirmReject) {
      setConfirmReject(true);
      return;
    }
    decideException.mutate({
      exceptionId: exception.exception_id,
      decision: "reject",
      decidedBy: currentUser.id,
      reason: "Rejected via dashboard",
    });
    setConfirmReject(false);
  };

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">Exception Review</h1>
          <div className="flex items-center gap-3 mt-1">
            <MonoText className="text-xs">{exception.exception_id}</MonoText>
            <MonoText className="text-xs text-clinical-cyan">{exception.project_id}</MonoText>
          </div>
        </div>
        <StatusBadge status={exception.status as ApprovalStatus} />
      </div>

      <Link to="/approvals" className="text-clinical-cyan text-xs font-mono hover:underline mb-6 block">
        ← Back to clearance queue
      </Link>

      {/* Exception details */}
      <VaultCard className="mb-6 border-clinical-cyan/20">
        <h2 className="vault-heading text-xs mb-3 text-clinical-cyan">Exception Record</h2>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 mb-3">
          <div>
            <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Requested By</p>
            <MonoText className="text-xs">{exception.requested_by}</MonoText>
          </div>
          <div>
            <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Status</p>
            <MonoText className="text-xs">{exception.status}</MonoText>
          </div>
          {exception.created_at && (
            <div>
              <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Submitted</p>
              <MonoText className="text-xs">{formatTimestamp(exception.created_at)}</MonoText>
            </div>
          )}
          {exception.expires_at && (
            <div>
              <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Expires</p>
              <MonoText className="text-xs">{formatTimestamp(exception.expires_at)}</MonoText>
            </div>
          )}
        </div>

        <div className="mb-3">
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-1">Rationale</p>
          <p className="text-xs font-mono text-bone-muted leading-relaxed bg-vault-black/40 rounded px-3 py-2">
            {exception.rationale}
          </p>
        </div>

        {compensatingControls.length > 0 && (
          <div>
            <p className="text-[10px] font-heading uppercase text-bone-dim mb-1">Compensating Controls</p>
            <ul className="space-y-0.5">
              {compensatingControls.map((c, i) => (
                <li key={i} className="text-xs font-mono text-bone-muted">{"\u2022"} {c}</li>
              ))}
            </ul>
          </div>
        )}

        {exception.scope && Object.keys(exception.scope).length > 0 && (
          <div className="mt-3">
            <p className="text-[10px] font-heading uppercase text-bone-dim mb-1">Scope</p>
            <pre className="font-mono text-xs text-bone-muted bg-vault-black/40 rounded px-3 py-2 whitespace-pre-wrap">
              {JSON.stringify(exception.scope, null, 2)}
            </pre>
          </div>
        )}
      </VaultCard>

      {/* Action bar */}
      {isPending && (
        <div className="border-t border-slate-border pt-4">
          <div className="flex gap-2">
            <button
              className="btn-teal"
              onClick={handleApprove}
              disabled={decideException.isPending}
            >
              <CheckCircle size={14} /> Approve
            </button>
            <button
              className={`${confirmReject ? "btn-danger ring-2 ring-dried-blood-bright/50" : "btn-danger"}`}
              onClick={handleReject}
              disabled={decideException.isPending}
            >
              <XCircle size={14} /> {confirmReject ? "Confirm Reject" : "Reject"}
            </button>
          </div>
          {confirmReject && (
            <p className="text-xs text-dried-blood-bright font-mono mt-2">
              Click Confirm Reject again to permanently reject this exception.
            </p>
          )}
        </div>
      )}

      {!isPending && (
        <VaultCard className="mt-4 border-slate-border/50">
          <p className="text-xs font-mono text-bone-dim">
            This exception is <span className="text-bone">{exception.status}</span>.
            {exception.approved_by && exception.approved_by.length > 0 && (
              <> Decided by: {exception.approved_by.join(", ")}</>
            )}
          </p>
        </VaultCard>
      )}
    </div>
  );
}
