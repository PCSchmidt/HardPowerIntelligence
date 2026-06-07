import "server-only";

import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { ApiResult } from "@/lib/types";

const BASE_URL = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000/v1";

// Server-side fetch to the FastAPI boundary. Attaches the caller's Supabase
// access token as a Bearer credential so FastAPI can verify + tier-gate.
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const supabase = await createSupabaseServerClient();
  // getUser() validates + hydrates the session from cookies; without it,
  // getSession() can return null in Server Components (@supabase/ssr quirk).
  await supabase.auth.getUser();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const token = session?.access_token;
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch (e) {
    console.error(`[apiFetch] ${path} fetch threw:`, (e as { cause?: { code?: string } })?.cause?.code ?? e);
    return { data: null, status: 503, error: { code: "api_unreachable", message: "API unreachable" } };
  }

  if (!res.ok) {
    let error;
    try {
      error = (await res.json()).error;
    } catch {
      error = { code: "http_error", message: `HTTP ${res.status}` };
    }
    console.error(`[apiFetch] ${path} -> HTTP ${res.status} ${error?.code ?? ""}`);
    return { data: null, status: res.status, error };
  }

  const data = (await res.json()) as T;
  return { data, status: res.status };
}
