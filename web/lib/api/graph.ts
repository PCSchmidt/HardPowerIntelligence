import { apiFetch } from "@/lib/api/client";
import type { ConvergenceGraph, EdgeCoappearances } from "@/lib/types";

export interface GraphQuery {
  desk?: string;
  days?: number;
  minConfidence?: number;
  crossDeskOnly?: boolean;
  funding?: boolean;
  limit?: number;
}

// GET /graph/convergence — the curated CONVERGES_WITH subgraph (§2), optionally overlaid with the
// AWARDED federal-funding subgraph (§5, funding=true).
export function getConvergenceGraph(q: GraphQuery = {}) {
  const params = new URLSearchParams();
  if (q.desk) params.set("desk", q.desk);
  if (q.days != null) params.set("days", String(q.days));
  if (q.minConfidence != null) params.set("min_confidence", String(q.minConfidence));
  if (q.crossDeskOnly) params.set("cross_desk_only", "true");
  if (q.funding) params.set("funding", "true");
  if (q.limit != null) params.set("limit", String(q.limit));
  const qs = params.toString();
  return apiFetch<ConvergenceGraph>(`/graph/convergence${qs ? `?${qs}` : ""}`);
}

// The published items where two entities both appear — the evidence behind an edge.
export function getEdgeCoappearances(a: string, b: string) {
  return apiFetch<EdgeCoappearances>(
    `/graph/co-appearances?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
  );
}
