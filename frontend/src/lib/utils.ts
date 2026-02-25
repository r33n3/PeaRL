import type { Environment, Severity, ApprovalStatus } from "./types";

export function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function severityClass(severity: Severity): string {
  const map: Record<Severity, string> = {
    critical: "badge-critical",
    high: "badge-high",
    moderate: "badge-moderate",
    low: "badge-low",
    info: "badge-info",
  };
  return map[severity] ?? "badge-info";
}

export function statusClass(status: ApprovalStatus): string {
  const map: Record<ApprovalStatus, string> = {
    pending: "badge-pending",
    approved: "badge-approved",
    rejected: "badge-rejected",
    expired: "badge-moderate",
    needs_info: "badge-needs-info",
  };
  return map[status] ?? "badge-info";
}

export function envClass(env: Environment | string): string {
  const map: Record<string, string> = {
    sandbox: "env-sandbox",
    dev: "env-dev",
    pilot: "env-pilot",
    preprod: "env-preprod",
    prod: "env-prod",
  };
  return map[env] ?? "env-sandbox";
}

export function ageColor(iso: string | null): string {
  if (!iso) return "text-bone-muted";
  const hours = (Date.now() - new Date(iso).getTime()) / 3600000;
  if (hours < 24) return "text-bone-muted";
  if (hours < 48) return "text-clinical-cyan";
  return "text-dried-blood-bright";
}

export function pct(n: number): string {
  return `${Math.round(n * 100) / 100}%`;
}
