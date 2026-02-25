import type { Severity } from "@/lib/types";
import { severityClass } from "@/lib/utils";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={severityClass(severity)}>{severity}</span>;
}
