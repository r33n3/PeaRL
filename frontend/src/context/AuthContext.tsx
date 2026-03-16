import { createContext, useContext, useState, useEffect, useCallback } from "react";

const BASE_URL = "/api/v1";

const STORAGE_ACCESS  = "pearl_access_token";
const STORAGE_REFRESH = "pearl_refresh_token";

export interface AuthUser {
  sub: string;
  roles: string[];
  email?: string;
  display_name?: string;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ── JWT helpers (no external library needed — we just decode the payload) ──────

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const b64 = parts[1] ?? "";
    const payload = atob(b64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return Date.now() / 1000 > payload.exp - 30; // 30s buffer
}

// ── Provider ───────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  // Attempt to load user from stored tokens on mount
  useEffect(() => {
    (async () => {
      const stored = localStorage.getItem(STORAGE_ACCESS);
      const refresh = localStorage.getItem(STORAGE_REFRESH);

      if (!stored && !refresh) {
        setState({ user: null, accessToken: null, isLoading: false });
        return;
      }

      // If access token is still valid use it, otherwise try to refresh
      let token = stored;
      if (!token || isTokenExpired(token)) {
        token = refresh ? await attemptRefresh(refresh) : null;
      }

      if (token) {
        const user = await fetchMe(token);
        setState({ user, accessToken: token, isLoading: false });
      } else {
        localStorage.removeItem(STORAGE_ACCESS);
        localStorage.removeItem(STORAGE_REFRESH);
        setState({ user: null, accessToken: null, isLoading: false });
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? "Login failed");
    }

    const data = await res.json();
    const { access_token, refresh_token } = data;

    localStorage.setItem(STORAGE_ACCESS, access_token);
    if (refresh_token) localStorage.setItem(STORAGE_REFRESH, refresh_token);

    const user = await fetchMe(access_token);
    setState({ user, accessToken: access_token, isLoading: false });
  }, []);

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem(STORAGE_REFRESH);
    const token = localStorage.getItem(STORAGE_ACCESS);

    try {
      if (token) {
        await fetch(`${BASE_URL}/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ refresh_token: refresh ?? "" }),
        });
      }
    } catch {
      // best-effort
    }

    localStorage.removeItem(STORAGE_ACCESS);
    localStorage.removeItem(STORAGE_REFRESH);
    setState({ user: null, accessToken: null, isLoading: false });
  }, []);

  const hasRole = useCallback(
    (role: string) => state.user?.roles?.includes(role) ?? false,
    [state.user],
  );

  return (
    <AuthContext.Provider value={{ ...state, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// ── Internal helpers ───────────────────────────────────────────────────────────

async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${BASE_URL}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    // Fall back to decoding the JWT directly
    const payload = decodeJwtPayload(token);
    return {
      sub: (payload?.sub as string) ?? "unknown",
      roles: (payload?.roles as string[]) ?? [],
    };
  }
  const data = await res.json();
  return {
    sub: data.user_id,
    roles: data.roles ?? [],
    email: data.email,
    display_name: data.display_name,
  };
}

async function attemptRefresh(refreshToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem(STORAGE_ACCESS, data.access_token);
      if (data.refresh_token) localStorage.setItem(STORAGE_REFRESH, data.refresh_token);
      return data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}
