import type { BriefItem, Citation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { formatUsd, keyAmount } from "@/lib/amounts";
import { ITEM_BG, ITEM_ICON, ITEM_LABEL, ITEM_TEXT } from "@/lib/item-types";
import { distinctOutlets } from "@/lib/sources";

// "Today at a glance" (D084): a scannable ledger above the long read so a busy analyst
// gets the day in ~10 seconds. Each row links to its item; a type icon (D087) and a
// normalized magnitude bar answer "what kind?" and "compared to what?". Server
// Component — hash links scroll natively, no JS.

export function BriefGlance({ items, citations = [] }: { items: BriefItem[]; citations?: Citation[] }) {
  if (items.length === 0) return null;

  const rows = items.map((item) => ({ item, amount: keyAmount(item.headline, item.body) }));
  const maxAmount = Math.max(0, ...rows.map((r) => r.amount ?? 0));
  const total = rows.reduce((sum, r) => sum + (r.amount ?? 0), 0);
  // Source diversity (D133): distinct outlets across the brief, not the raw citation count —
  // a signal of how broadly the day was reported, shown alongside the item/$ totals.
  const sourceCount = distinctOutlets(citations).length;

  return (
    <section aria-label="At a glance" className="mt-8 rounded-md border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
        At a glance
        <span className="ml-auto font-normal normal-case">
          {items.length} item{items.length === 1 ? "" : "s"}
          {sourceCount > 0 && <> · {sourceCount} source{sourceCount === 1 ? "" : "s"}</>}
          {total > 0 && <> · ≈{formatUsd(total)} tracked</>} · 100% cited
        </span>
      </div>
      <ul className="divide-y divide-border">
        {rows.map(({ item, amount }) => {
          const Icon = ITEM_ICON[item.item_type];
          return (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className="group flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50"
            >
              <Icon size={14} className={cn("shrink-0", ITEM_TEXT[item.item_type])} />
              <span className="w-14 shrink-0 text-ui-xs uppercase tracking-wide text-muted-foreground">
                {ITEM_LABEL[item.item_type]}
              </span>
              <span className="min-w-0 flex-1 truncate text-ui-md text-foreground group-hover:underline">
                {item.headline}
              </span>
              {amount !== null && (
                <span className="hidden shrink-0 items-center gap-2 sm:flex">
                  <span className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                    <span
                      className={cn("block h-full rounded-full", ITEM_BG[item.item_type])}
                      style={{ width: `${maxAmount ? (amount / maxAmount) * 100 : 0}%` }}
                    />
                  </span>
                  <span className="w-12 text-right text-ui-sm font-medium tabular-nums text-foreground">
                    {formatUsd(amount)}
                  </span>
                </span>
              )}
              <span className="w-12 shrink-0 text-right text-ui-xs text-muted-foreground">
                {item.citation_ids.length} src
              </span>
            </a>
          </li>
          );
        })}
      </ul>
    </section>
  );
}
