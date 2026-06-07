"use client";

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
        </article>
      ))}
      <CitationsDrawer citations={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
