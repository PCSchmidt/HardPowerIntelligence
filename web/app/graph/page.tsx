import type { Metadata } from "next";

import { getConvergenceGraph } from "@/lib/api/graph";
import { ConvergenceGraph } from "@/components/graph/convergence-graph";

// The convergence graph is a logged-in reader surface, not a marketing page.
export const metadata: Metadata = {
  title: "Convergence Graph",
  robots: { index: false, follow: false },
};

export default async function GraphPage() {
  const { data } = await getConvergenceGraph({ limit: 200 });

  return (
    <main className="mx-auto max-w-page px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-bold text-brand">Convergence Graph</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Entities that recur together across the Defense, AI, and Energy desks. A gold node or link
          spans more than one desk — the cross-sector convergence the briefs are built around. Hover an
          edge to see the stories behind a connection. The graph fills in and sharpens as more briefs publish.
        </p>
      </header>

      {!data || data.edges.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No convergence links yet. The graph appears once entities begin recurring together across
          desks — it builds up as the daily briefs accrue.
        </div>
      ) : (
        <ConvergenceGraph graph={data} />
      )}
    </main>
  );
}
