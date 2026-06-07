import { apiFetch } from "@/lib/api/client";
import type { AuthMe } from "@/lib/types";

export function getMe() {
  return apiFetch<AuthMe>("/auth/me");
}
