import Link from "next/link";
import { Sparkles } from "lucide-react";
import type { EntitySummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { entityDisplayName } from "@/lib/entities";

// Chips for the entities an item is about (T3.5, D091). Public companies show their ticker; a
// closely-held / venture entity (no ticker, minted from a CIK/UEI during resolution) shows a muted
// "private" tag. Resolved entities only render because the resolver cleared its accuracy eval gate
// (D091) — a wrong ticker would corrupt the provenance the product is built on.
export function EntityChips({
  entityIds,
  entities,
}: {
  entityIds: string[];
  entities: Map<string, EntitySummary>;
}) {
  const resolved = entityIds
    .map((id) => entities.get(id))
    .filter((e): e is EntitySummary => Boolean(e));

  if (resolved.length === 0) return null;

  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Entities">
      {resolved.map((entity) => (
        <li key={entity.id}>
          <Link
            href={`/entity/${entity.id}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-ui-xs text-foreground transition-colors",
              entity.convergence
                ? "border-brand-secondary/40 bg-brand-secondary/10 hover:bg-brand-secondary/20"
                : "border-border bg-muted/60 hover:border-primary/40 hover:bg-muted",
            )}
            title={entity.convergence ? "Appears across multiple desks (convergence)" : undefined}
          >
            {entity.convergence && (
              <Sparkles size={11} className="shrink-0 text-brand-secondary" aria-label="convergence" />
            )}
            <span className="font-medium">{entityDisplayName(entity.name)}</span>
            {entity.ticker ? (
              <span className="font-mono text-[0.7rem] font-semibold text-primary">{entity.ticker}</span>
            ) : (
              <span className="text-[0.7rem] uppercase tracking-wide text-muted-foreground">private</span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
