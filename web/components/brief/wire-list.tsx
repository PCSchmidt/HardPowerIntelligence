"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Desk, Wire } from "@/lib/types";
import { sourceName } from "@/lib/sources";
import { capture } from "@/lib/analytics";

// The Full Wire (D112): a no-narrative list of the material, on-thesis items that cleared
// scoring but lost the brief's space cut. Title + source + link, ranked by materiality, so a
// reader can see everything relevant — not just what fit the curated desk read.
export function WireList({ wire, deskLabel }: { wire: Wire; deskLabel: string }) {
  return (
    <div className="mx-auto max-w-content px-4 py-10 sm:px-6">
      <Link
        href={`/desk/${wire.desk}`}
        className="mb-6 inline-flex items-center gap-1 text-ui-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} /> Back to the {deskLabel} desk
      </Link>

      <h1 className="font-display text-h2 font-semibold text-foreground">{deskLabel} — Full Wire</h1>
      <p className="mt-2 max-w-prose text-body-sm text-muted-foreground">
        Everything material the {deskLabel} desk surfaced today that didn&apos;t fit the brief —
        ranked by signal, source-attributed, link-only. Nothing relevant gets thrown away.
      </p>

      {wire.items.length === 0 ? (
        <p className="mt-10 text-ui-md text-muted-foreground">
          Nothing overflowed today — the full read is on the{" "}
          <Link href={`/desk/${wire.desk}`} className="font-medium text-primary hover:underline">
            {deskLabel} desk
          </Link>
          .
        </p>
      ) : (
        <ul className="mt-8 space-y-3">
          {wire.items.map((item, i) => {
            const body = (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-ui-xs uppercase tracking-wide text-muted-foreground">
                  <span className="font-medium">{sourceName(item.source_id)}</span>
                  {item.item_type && (
                    <>
                      <span>·</span>
                      <span>{item.item_type.replace(/_/g, " ")}</span>
                    </>
                  )}
                </div>
                <p className="font-body text-body-sm font-medium text-foreground">{item.headline}</p>
                {item.url && (
                  <span className="inline-flex items-center gap-1 text-ui-sm font-medium text-primary group-hover:underline">
                    View source <ExternalLink size={14} />
                  </span>
                )}
              </div>
            );
            const className =
              "group block rounded-lg border border-border bg-background p-4 shadow-sm transition-colors hover:border-primary/40";
            return (
              <li key={`${item.source_id}-${item.native_id ?? i}`}>
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={className}
                    // A wire click is a ranking complaint in disguise (B1): this item lost the
                    // brief's space cut, and the reader went for it anyway. Enough of these on one
                    // source or item_type is direct evidence the significance gate ranked it wrong.
                    onClick={() =>
                      capture({
                        name: "wire_item_clicked",
                        desk: wire.desk,
                        source_id: item.source_id,
                        position: i,
                      })
                    }
                  >
                    {body}
                  </a>
                ) : (
                  <div className={className}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export const DESK_LABEL: Record<Desk, string> = {
  defense: "Defense",
  energy: "Energy",
  ai: "AI Infrastructure",
};
