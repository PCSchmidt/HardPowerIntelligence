import { apiFetch } from "@/lib/api/client";
import type { ConvergenceGraph } from "@/lib/types";

export interface GraphQuery {
  desk?: string;
  days?: number;
  minConfidence?: number;
  crossDeskOnly?: boolean;
  limit?: number;
}

// GET /graph/convergence — the curated CONVERGES_WITH subgraph (§2).
export function getConvergenceGraph(q: GraphQuery = {}) {
  const params = new URLSearchParams();
  if (q.desk) params.set("desk", q.desk);
  if (q.days != null) params.set("days", String(q.days));
  if (q.minConfidence != null) params.set("min_confidence", String(q.minConfidence));
  if (q.crossDeskOnly) params.set("cross_desk_only", "true");
  if (q.limit != null) params.set("limit", String(q.limit));
  const qs = params.toString();
  return apiFetch<ConvergenceGraph>(`/graph/convergence${qs ? `?${qs}` : ""}`);
}
