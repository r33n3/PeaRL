import type { ReactNode } from "react";

export function MonoText({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={`mono-data ${className}`}>{children}</span>;
}
