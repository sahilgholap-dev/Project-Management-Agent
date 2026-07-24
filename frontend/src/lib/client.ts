"use client";

// Client-component fetch helper for mutations through the /api rewrite proxy
// (plan section 4: no client cache, no optimistic UI — callers router.refresh()
// after a successful mutation so the screen shows post-mutation truth).

export async function apiFetch<T = unknown>(
  path: string,
  options?: { method?: string; body?: unknown },
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: options?.method ?? "GET",
    headers: options?.body !== undefined
      ? { "content-type": "application/json" }
      : undefined,
    body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail ?? "request failed"),
    );
  }
  return data as T;
}
