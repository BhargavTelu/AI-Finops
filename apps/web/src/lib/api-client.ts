// Thin wrapper around fetch for calling the FastAPI backend.
// Attaches Clerk session token automatically.
// All methods throw on non-2xx responses (Problem+JSON format).

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function request<T>(
  path: string,
  token: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, method, ...init } = options;
  const isGet = !method || method === "GET";

  const response = await fetch(`${API_URL}/api/v1${path}`, {
    method,
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // Clerk auth() marks routes as dynamic, which makes Next.js default every
    // fetch to no-store. Explicitly opt GET responses into the Data Cache so
    // re-visiting a tab skips the FastAPI + Supabase round-trip for 2 minutes.
    // Mutations stay uncached to guarantee fresh data after writes.
    ...(isGet ? { next: { revalidate: 120 } } : { cache: "no-store" as const }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail ?? "Request failed");
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// Factory: call with a Clerk session token to get a typed client.
export function createApiClient(token: string) {
  return {
    get: <T>(path: string) => request<T>(path, token),
    post: <T>(path: string, body: unknown) =>
      request<T>(path, token, { method: "POST", body }),
    patch: <T>(path: string, body: unknown) =>
      request<T>(path, token, { method: "PATCH", body }),
    delete: (path: string) => request<void>(path, token, { method: "DELETE" }),
  };
}
