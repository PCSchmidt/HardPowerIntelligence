import type { Attribution } from "./types";

// Single source of truth for the per-item confidence/attribution chip (D098/D099).
// The chip shows the BASIS of an item — transparency, the way real intelligence analysis
// uses estimative language — so the reader weighs each item by its confidence tier.

export const ATTRIBUTION_LABEL: Record<Attribution, string> = {
  confirmed: "Confirmed",
  reported: "Reported",
  analysis: "HPI analysis",
  speculative: "Speculative",
};

// One-line basis explanation (chip tooltip / aria-label).
export const ATTRIBUTION_TOOLTIP: Record<Attribution, string> = {
  confirmed: "Primary public record, supported by the cited source",
  reported: "Attributed third-party reporting — named, not a primary record",
  analysis: "HPI synthesis or inference connecting the records",
  speculative: "An early or weak signal worth watching; low confidence",
};

// Subtle tinted chip per tier, descending certainty: confirmed (emerald) → reported
// (sky) → analysis (amber) → speculative (muted).
export const ATTRIBUTION_CLASS: Record<Attribution, string> = {
  confirmed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  reported: "bg-sky-500/10 text-sky-700 dark:text-sky-400",
  analysis: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  speculative: "bg-muted text-muted-foreground",
};

// Fallback so a missing/unknown value never breaks the render (pre-D099 rows, etc.).
export function attributionOf(value: string | null | undefined): Attribution {
  return value && value in ATTRIBUTION_LABEL ? (value as Attribution) : "confirmed";
}
