import type { ApprovalStatus } from "@/lib/types";
import { statusClass } from "@/lib/utils";

const LABELS: Record<string, string> = {
  pending: "pending",
  approved: "approved",
  rejected: "rejected",
  expired: "expired",
  needs_info: "needs info",
};

export function StatusBadge({ status }: { status: ApprovalStatus }) {
  return (
    <span className={statusClass(status)}>
      {LABELS[status] ?? status}
    </span>
  );
}
