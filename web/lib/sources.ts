// Pretty display names for raw source_id values (D084). Used by the citations drawer
// and the at-a-glance ledger so provenance reads like a credential, not a slug.
const SOURCE_NAMES: Record<string, string> = {
  edgar: "SEC EDGAR",
  usaspending: "USASpending.gov",
  arxiv: "arXiv",
  gdelt: "GDELT",
  sam_gov: "SAM.gov",
  congress_gov: "Congress.gov",
  fred: "FRED",
  dod_contracts: "DoD Contracts",
};

export function sourceName(sourceId: string): string {
  return SOURCE_NAMES[sourceId] ?? sourceId;
}

import type { Citation } from "./types";

// Bare outlet host (drop www.) so we name the actual publication — e.g. "navalnews.com" —
// rather than the internal source_id ("feeds"). Bad/relative URLs → "".
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// Distinct outlet domains across a set of citations, in first-seen order. This is the diversity
// signal a reader cares about ("drawn from N publications"), not the raw citation count — three
// articles from one outlet are one source of information, not three.
export function distinctOutlets(cites: Citation[]): string[] {
  const seen: string[] = [];
  for (const c of cites) {
    const h = hostOf(c.url);
    if (h && !seen.includes(h)) seen.push(h);
  }
  return seen;
}
