import Link from "next/link";
import { Sparkles } from "lucide-react";
import type { EntityDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ITEM_ICON, ITEM_LABEL, ITEM_TEXT } from "@/lib/item-types";
import { deskLabel, entityDisplayName, ID_TYPE_LABEL } from "@/lib/entities";

// Entity 360 (T3.6, D091) — the resolved entity's identity card: identifiers, the desks it spans
// (the cross-desk convergence signal), and where it's recently appeared, each linking back to its
// brief. Backed by the resolution graph (the moat); this is the page the brief chips link into.
export function Entity360({ entity }: { entity: EntityDetail }) {
  const name = entityDisplayName(entity.name);
  return (
    <div className="mx-auto max-w-content px-4 py-10 sm:px-6">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-display-md text-foreground">{name}</h1>
          {entity.ticker ? (
            <span className="rounded-md bg-primary/10 px-2 py-0.5 font-mono text-ui-sm font-semibold text-primary">
              {entity.ticker}
            </span>
          ) : (
            <span className="rounded-md bg-muted px-2 py-0.5 text-ui-xs uppercase tracking-wide text-muted-foreground">
              Private company
            </span>
          )}
        </div>

        {entity.desks.length > 0 && (
          <div
            className={cn(
              "mt-4 flex flex-wrap items-center gap-2 text-ui-sm",
              entity.convergence ? "text-brand-secondary" : "text-muted-foreground",
            )}
          >
            {entity.convergence && <Sparkles size={15} className="shrink-0" />}
            <span>
              {entity.convergence ? "Convergence — appears across " : "Appears on "}
              <span className="font-medium text-foreground">
                {entity.desks.map(deskLabel).join(" · ")}
              </span>
            </span>
          </div>
        )}
      </header>

      {entity.identifiers.length > 0 && (
        <section className="border-b border-border py-6">
          <h2 className="mb-3 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
            Identifiers
          </h2>
          <dl className="flex flex-wrap gap-x-8 gap-y-2">
            {entity.identifiers.map((id) => (
              <div key={`${id.type}-${id.value}`} className="text-ui-sm">
                <dt className="text-muted-foreground">{ID_TYPE_LABEL[id.type] ?? id.type}</dt>
                <dd className="font-mono text-foreground">{id.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="py-6">
        <h2 className="mb-3 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
          Recent appearances
        </h2>
        {entity.appearances.length === 0 ? (
          <p className="text-ui-sm text-muted-foreground">
            No briefs reference this entity yet.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {entity.appearances.map((a, i) => {
              const Icon = ITEM_ICON[a.item_type];
              return (
                <li key={`${a.brief_id}-${i}`}>
                  <Link
                    href={`/brief/${a.brief_id}`}
                    className="flex items-start gap-3 py-3 hover:bg-muted/40"
                  >
                    <Icon size={15} className={cn("mt-0.5 shrink-0", ITEM_TEXT[a.item_type])} />
                    <div className="min-w-0">
                      <p className="text-ui-sm text-foreground">{a.headline}</p>
                      <p className="mt-0.5 text-ui-xs text-muted-foreground">
                        {deskLabel(a.desk)} · {ITEM_LABEL[a.item_type]} · {a.date}
                      </p>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <p className="mt-2 text-ui-xs italic text-muted-foreground">
        Deeper entity intelligence — filings, contract history, and supply-chain links — is on the
        way. Source-grounded research, not investment advice.
      </p>
    </div>
  );
}
