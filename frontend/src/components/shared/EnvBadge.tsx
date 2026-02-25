import type { Environment } from "@/lib/types";
import { envClass } from "@/lib/utils";

export function EnvBadge({ env }: { env: Environment | string }) {
  return <span className={envClass(env)}>{env}</span>;
}
