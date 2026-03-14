const BASE_URL = "/api/v1";

// Bootstrap API key — set VITE_API_KEY in .env.local or docker-compose environment
const API_KEY = (import.meta.env.VITE_API_KEY as string) || undefined;

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const authHeaders: Record<string, string> = API_KEY
    ? { "X-API-Key": API_KEY }
    : {};

  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
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
