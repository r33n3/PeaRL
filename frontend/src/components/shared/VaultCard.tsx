import type { CSSProperties, ReactNode } from "react";

export interface VaultCardProps {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}

export function VaultCard({
  children,
  className = "",
  interactive = false,
  onClick,
  style,
}: VaultCardProps) {
  const base = interactive ? "vault-card-interactive" : "vault-card";
  return (
    <div className={`${base} p-4 ${className}`} onClick={onClick} style={style}>
      {children}
    </div>
  );
}
