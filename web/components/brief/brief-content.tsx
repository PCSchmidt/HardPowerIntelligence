"use client";

import { ChevronDown, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import type { BriefItem, Citation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CitationsDrawer } from "./citations-drawer";

const ITEM_LABEL: Record<BriefItem["item_type"], string> = {
  award: "Award",
  filing: "Filing",
  policy: "Policy",
  macro: "Macro",
  signal: "Signal",
};

const ITEM_DOT: Record<BriefItem["item_type"], string> = {
  award: "bg-item-award",
  filing: "bg-item-filing",
  policy: "bg-item-policy",
  macro: "bg-item-macro",
  signal: "bg-item-signal",
};

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
}: {
  items: BriefItem[];
  citations: Citation[];
}) {
  const [drawer, setDrawer] = useState<Citation[] | null>(null);
  const citationById = useMemo(
    () => new Map(citations.map((c) => [c.id, c])),
    [citations],
  );

  function openForItem(item: BriefItem) {
    const list = item.citation_ids
      .map((id) => citationById.get(id))
      .filter((c): c is Citation => Boolean(c));
    setDrawer(list);
  }

  return (
    <div className="divide-y divide-border">
      {items.map((item) => (
        <article key={item.id} className="space-y-3 py-8">
          <div className="flex items-center gap-2 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
            <span className={cn("size-2 rounded-full", ITEM_DOT[item.item_type])} />
            {ITEM_LABEL[item.item_type]}
          </div>
          <h2 className="font-display text-display-sm text-foreground">{item.headline}</h2>
          <CitedBody body={item.body} onCite={() => openForItem(item)} />
          {(item.read || item.watch) && (
            <AnalysisDisclosure read={item.read} watch={item.watch} />
          )}
        </article>
      ))}
      <CitationsDrawer citations={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
