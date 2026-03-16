const BASE_URL = "/api/v1";

// Bootstrap API key — fallback when no JWT session is active
const BOOTSTRAP_API_KEY = (import.meta.env.VITE_API_KEY as string) || undefined;

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("pearl_access_token");
  if (token) return { Authorization: `Bearer ${token}` };
  if (BOOTSTRAP_API_KEY) return { "X-API-Key": BOOTSTRAP_API_KEY };
  return {};
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
