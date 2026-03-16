import { useState, FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ShieldCheck, LogIn, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const from = (location.state as { from?: string })?.from ?? "/";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen bg-vault-black overflow-hidden">
      {/* ── Left panel — branding ───────────────────────────────────── */}
      <div className="hidden lg:flex w-1/2 flex-col justify-center items-center px-16 border-r border-slate-border relative">
        {/* Subtle grid texture */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(#c8c2b8 1px, transparent 1px), linear-gradient(90deg, #c8c2b8 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />

        <div className="relative z-10 text-center">
          <div className="flex items-center justify-center gap-3 mb-6">
            <ShieldCheck size={40} className="text-cold-teal" strokeWidth={1.5} />
          </div>

          <h1 className="font-heading text-5xl font-bold tracking-widest uppercase pearl-wordart mb-3">
            PeaRL
          </h1>

          <p className="mono-data text-base mb-2 text-bone-muted">
            Policy-enforced Autonomous Risk Layer
          </p>
          <p className="text-xs text-bone-dim font-mono">
            AI Governance · Risk Orchestration · Gate Enforcement
          </p>

          {/* Decorative rule */}
          <div className="mt-10 flex items-center gap-4">
            <div className="flex-1 h-px bg-slate-border" />
            <span className="text-xs font-mono text-bone-dim uppercase tracking-widest">
              v1.1.0
            </span>
            <div className="flex-1 h-px bg-slate-border" />
          </div>

          {/* Role legend */}
          <div className="mt-8 grid grid-cols-2 gap-2 max-w-xs mx-auto text-left">
            {[
              { role: "viewer",          desc: "Read-only access" },
              { role: "operator",        desc: "Submit & ingest" },
              { role: "reviewer",        desc: "Approve gates" },
              { role: "admin",           desc: "Full management" },
            ].map(({ role, desc }) => (
              <div
                key={role}
                className="px-3 py-2 bg-charcoal border border-slate-border rounded-md"
              >
                <div className="text-xs font-heading font-semibold uppercase tracking-wider text-cold-teal">
                  {role}
                </div>
                <div className="text-xs text-bone-dim font-mono mt-0.5">{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right panel — login form ────────────────────────────────── */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center items-center px-8">
        {/* Mobile logo */}
        <div className="flex lg:hidden items-center gap-2 mb-8">
          <ShieldCheck size={22} className="text-cold-teal" strokeWidth={1.5} />
          <h1 className="font-heading text-2xl font-bold tracking-widest uppercase pearl-wordart">
            PeaRL
          </h1>
        </div>

        <div className="w-full max-w-sm">
          {/* Card */}
          <div className="vault-card p-8">
            <div className="mb-7">
              <h2 className="vault-heading text-lg mb-1">Sign In</h2>
              <p className="text-xs text-bone-dim font-mono">
                Use your PeaRL account credentials
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Email */}
              <div>
                <label className="block text-xs font-heading font-semibold uppercase tracking-wider text-bone-muted mb-1.5">
                  Email
                </label>
                <input
                  className="input-vault"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              {/* Password */}
              <div>
                <label className="block text-xs font-heading font-semibold uppercase tracking-wider text-bone-muted mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <input
                    className="input-vault pr-10"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    disabled={loading}
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-bone-dim hover:text-bone-muted transition-colors"
                    onClick={() => setShowPassword((v) => !v)}
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* Error */}
              {error && (
                <div className="flex items-start gap-2 px-3 py-2.5 bg-dried-blood/10 border border-dried-blood/30 rounded-md text-xs text-dried-blood-bright font-mono animate-fade-in">
                  <span className="shrink-0 mt-0.5">✕</span>
                  <span>{error}</span>
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading || !email || !password}
                className="btn-teal w-full mt-1"
              >
                {loading ? (
                  <>
                    <span className="inline-block w-3.5 h-3.5 border-2 border-cold-teal/30 border-t-cold-teal rounded-full animate-spin" />
                    Authenticating…
                  </>
                ) : (
                  <>
                    <LogIn size={14} />
                    Sign In
                  </>
                )}
              </button>
            </form>
          </div>

          <p className="text-center text-xs text-bone-dim font-mono mt-4">
            Access governed by PeaRL RBAC policy
          </p>
        </div>
      </div>
    </div>
  );
}
