import { apiFetch } from "@/lib/api/client";
import type { Brief, Desk } from "@/lib/types";

export function getLatestBrief(desk: Desk) {
  return apiFetch<Brief>(`/briefs/latest?desk=${desk}`);
}

export function getBrief(id: string) {
  return apiFetch<Brief>(`/briefs/${id}`);
}
