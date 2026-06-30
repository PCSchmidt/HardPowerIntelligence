import { apiFetch } from "@/lib/api/client";
import type { Desk, Wire } from "@/lib/types";

// The desk's "Full Wire" (D112): material, on-thesis items that cleared scoring but lost
// the brief's space cut. Tied to the desk's latest published brief; same access as it.
export function getLatestWire(desk: Desk) {
  return apiFetch<Wire>(`/wire/latest?desk=${desk}`);
}
