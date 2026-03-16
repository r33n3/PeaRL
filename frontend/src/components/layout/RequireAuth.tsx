import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-vault-black">
        <div className="flex flex-col items-center gap-3">
          <span className="inline-block w-6 h-6 border-2 border-cold-teal/30 border-t-cold-teal rounded-full animate-spin" />
          <span className="text-xs font-mono text-bone-dim uppercase tracking-widest">
            Verifying session…
          </span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <>{children}</>;
}
