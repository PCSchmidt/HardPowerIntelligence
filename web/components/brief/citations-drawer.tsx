"use client";

import { ExternalLink, X } from "lucide-react";
import type { Citation } from "@/lib/types";
import { sourceName } from "@/lib/sources";

// Slide-in citations panel. Right overlay on lg+, bottom sheet on mobile (D023).
// Rendered open when `citations` is non-null.
export function CitationsDrawer({
  citations,
  onClose,
}: {
  citations: Citation[] | null;
  onClose: () => void;
}) {
  if (!citations) return null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-foreground/20" onClick={onClose} aria-hidden />
      <aside
        className="fixed z-50 flex flex-col gap-4 overflow-y-auto bg-card p-6 shadow-drawer
          inset-x-0 bottom-0 max-h-[80vh] rounded-t-xl animate-fade-in
          lg:inset-y-0 lg:right-0 lg:bottom-auto lg:left-auto lg:w-[420px] lg:max-h-none lg:rounded-none lg:animate-slide-in-right"
        role="dialog"
        aria-label="Citations"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-display-sm">Sources</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 hover:bg-muted"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        {citations.length === 0 ? (
          <p className="text-ui-md text-muted-foreground">No sources for this item.</p>
        ) : (
          citations.map((c) => (
            <div key={c.id} className="space-y-1 rounded-lg border border-border bg-background p-4 shadow-sm">
              <div className="flex items-center gap-2 text-ui-xs uppercase tracking-wide text-muted-foreground">
                <span className="font-medium">{sourceName(c.source_id)}</span>
                <span>·</span>
                {/* Show the SOURCE's publication date (staleness signal); fall back to our
                    retrieval date, clearly labelled, when the source has no usable date (D129). */}
                <span>
                  {c.published_at
                    ? `Published ${new Date(c.published_at).toLocaleDateString("en-US", { timeZone: "UTC" })}`
                    : `Retrieved ${new Date(c.fetched_at).toLocaleDateString("en-US", { timeZone: "UTC" })}`}
                </span>
              </div>
              {c.title && <p className="font-body text-body-sm font-medium text-foreground">{c.title}</p>}
              {c.excerpt && <p className="font-body text-body-sm text-muted-foreground">{c.excerpt}</p>}
              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-ui-sm font-medium text-primary hover:underline"
              >
                View source <ExternalLink size={14} />
              </a>
            </div>
          ))
        )}
      </aside>
    </>
  );
}
