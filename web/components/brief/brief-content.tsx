"use client";

import { ChevronDown, FileText, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import type { BriefItem, Citation, EntitySummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { classifyAmount, formatUsd } from "@/lib/amounts";
import { ITEM_BG, ITEM_ICON, ITEM_LABEL, ITEM_TEXT } from "@/lib/item-types";
import {
  ATTRIBUTION_CLASS,
  ATTRIBUTION_LABEL,
  ATTRIBUTION_TOOLTIP,
  attributionOf,
} from "@/lib/attribution";
import { distinctOutlets } from "@/lib/sources";
import { CitationsDrawer } from "./citations-drawer";
import { EntityChips } from "./entity-chips";

// At-a-glance provenance for a card footer: which publications, and how fresh — without
// opening the drawer. Distinct outlets (first two + "+N") and the most recent date, labelled
// "Published" when the source dated itself, else "Retrieved" (its fetch time) so a missing
// publication date degrades rather than hides (never drop a source for lacking a date).
function sourceSummary(cites: Citation[]): { outlets: string; dateLabel: string | null } {
  const domains = distinctOutlets(cites);
  const outlets =
    domains.length <= 2
      ? domains.join(", ")
      : `${domains.slice(0, 2).join(", ")} +${domains.length - 2}`;

  const fmt = (d: string) => new Date(d).toLocaleDateString("en-US", { timeZone: "UTC" });
  const latest = (ds: string[]) => ds.reduce((a, b) => (a > b ? a : b)); // ISO-8601 → lexical max
  const published = cites.map((c) => c.published_at).filter((d): d is string => Boolean(d));
  if (published.length > 0) return { outlets, dateLabel: `Published ${fmt(latest(published))}` };
  const fetched = cites.map((c) => c.fetched_at).filter(Boolean);
  if (fetched.length > 0) return { outlets, dateLabel: `Retrieved ${fmt(latest(fetched))}` };
  return { outlets, dateLabel: null };
}

// Splits a body string on [CITE:N] markers and renders each as a clickable chip.
function CitedBody({ body, onCite }: { body: string; onCite: () => void }) {
  const parts = body.split(/(\[CITE:\d+\])/g);
  return (
    <p className="prose-brief">
      {parts.map((part, i) => {
        const m = part.match(/^\[CITE:(\d+)\]$/);
        if (m) {
          return (
            <button
              key={i}
              type="button"
              onClick={onCite}
              className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-sm bg-primary/10 px-1 align-super text-[0.65rem] font-medium text-primary hover:bg-primary/20"
            >
              {m[1]}
            </button>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

// Drill-down for the analysis layer (D071/D073): collapsed by default so the cited
// ledger stays scannable; expands to the grounded HPI interpretation. Only rendered
// when the grounding gate kept a read/watch — an empty field is simply absent.
function AnalysisDisclosure({ read, watch }: { read: string; watch: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-brand-secondary/30 bg-muted/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open ? "true" : "false"}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-ui-xs font-medium uppercase tracking-wide text-brand-secondary"
      >
        <Sparkles size={14} className="shrink-0" />
        Analysis — HPI interpretation
        <ChevronDown
          size={16}
          className={cn("ml-auto shrink-0 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="space-y-4 px-4 pb-4">
          {read && <p className="prose-brief text-foreground">{read}</p>}
          {watch && (
            <div>
              <div className="mb-1 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
                What to watch
              </div>
              <p className="prose-brief text-foreground">{watch}</p>
            </div>
          )}
          <p className="text-ui-xs italic text-muted-foreground">
            HPI interpretation grounded in the cited facts — not investment advice.
          </p>
        </div>
      )}
    </div>
  );
}

// Interactive brief body (Client Component): renders ordered items and the
// citations drawer they open.
export function BriefContent({
  items,
  citations,
  entities,
}: {
  items: BriefItem[];
  citations: Citation[];
  entities: EntitySummary[];
}) {
  const [drawer, setDrawer] = useState<Citation[] | null>(null);
  const citationById = useMemo(
    () => new Map(citations.map((c) => [c.id, c])),
    [citations],
  );
  const entityById = useMemo(
    () => new Map(entities.map((e) => [e.id, e])),
    [entities],
  );

  // Inline magnitude bars (D087): each item's key dollar figure, normalized to the
  // largest in the brief, so a number reads "compared to what?" right at the item.
  const rows = useMemo(
    () =>
      items.map((item) => ({
        item,
        amount: classifyAmount(item.headline, item.body),
        cites: item.citation_ids
          .map((id) => citationById.get(id))
          .filter((c): c is Citation => Boolean(c)),
      })),
    [items, citationById],
  );
  // Scale bars against the largest *tracked* figure only (D138) — a market projection is shown
  // with a "projected" tag, not a proportional bar, so it can't flatten every real deal's bar.
  const maxAmount = Math.max(0, ...rows.map((r) => (r.amount?.kind === "tracked" ? r.amount.value : 0)));

  return (
    <div className="divide-y divide-border">
      {rows.map(({ item, amount, cites }) => {
        const Icon = ITEM_ICON[item.item_type];
        const attribution = attributionOf(item.attribution);
        return (
        <article key={item.id} id={item.id} className="scroll-mt-20 space-y-3 py-8">
          <div className="flex items-center gap-2 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Icon size={14} className={cn("shrink-0", ITEM_TEXT[item.item_type])} />
            {ITEM_LABEL[item.item_type]}
            <span
              className={cn(
                "rounded-sm px-1.5 py-0.5 text-[0.6rem] normal-case tracking-normal",
                ATTRIBUTION_CLASS[attribution],
              )}
              title={ATTRIBUTION_TOOLTIP[attribution]}
            >
              {ATTRIBUTION_LABEL[attribution]}
            </span>
            {amount !== null && (
              <span className="ml-auto flex items-center gap-2 normal-case tracking-normal">
                {amount.kind === "tracked" ? (
                  <span className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-muted sm:block">
                    <span
                      className={cn("block h-full rounded-full", ITEM_BG[item.item_type])}
                      style={{ width: `${maxAmount ? (amount.value / maxAmount) * 100 : 0}%` }}
                    />
                  </span>
                ) : (
                  // Projection (D138): a tag, not a proportional bar — never on the tracked-capital scale.
                  <span className="rounded-sm border border-dashed border-muted-foreground/40 px-1 text-[0.6rem] uppercase tracking-wide text-muted-foreground">
                    projected
                  </span>
                )}
                <span
                  className={cn(
                    "font-medium tabular-nums",
                    amount.kind === "tracked" ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {formatUsd(amount.value)}
                </span>
              </span>
            )}
          </div>
          <h2 className="font-display text-display-sm text-foreground">{item.headline}</h2>
          <EntityChips entityIds={item.entity_ids} entities={entityById} />
          <CitedBody body={item.body} onCite={() => setDrawer(cites)} />
          {(item.read || item.watch) && (
            <AnalysisDisclosure read={item.read} watch={item.watch} />
          )}
          {cites.length > 0 &&
            (() => {
              // At-a-glance provenance line: outlet(s) + freshness on the card itself, so the
              // reader judges "what publication / how stale" without opening the drawer. Whole
              // row still opens the drawer for the claim-level (per-sentence) citations.
              const { outlets, dateLabel } = sourceSummary(cites);
              return (
                <button
                  type="button"
                  onClick={() => setDrawer(cites)}
                  className="group flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-left text-ui-sm text-muted-foreground"
                >
                  <FileText size={14} className="shrink-0 text-primary" />
                  <span className="font-medium text-primary group-hover:underline">
                    Sources ({cites.length})
                  </span>
                  {outlets && <span>· {outlets}</span>}
                  {dateLabel && <span>· {dateLabel}</span>}
                </button>
              );
            })()}
        </article>
        );
      })}
      <CitationsDrawer citations={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
