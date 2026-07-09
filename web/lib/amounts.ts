// Parse the key dollar figure out of brief text for the at-a-glance magnitude bars (D084).
// The headline carries the salient number ("…for $55.9M", "…$700M Subscription"), so we read
// the headline first and fall back to the largest figure in the body. Display-only; the
// authoritative facts remain the cited body text.
const SCALE: Record<string, number> = {
  trillion: 1e12,
  t: 1e12,
  billion: 1e9,
  bn: 1e9,
  b: 1e9,
  million: 1e6,
  mm: 1e6,
  mn: 1e6,
  m: 1e6,
  thousand: 1e3,
  k: 1e3,
};

const AMOUNT_RE = /\$\s*([\d][\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand|bn|mm|mn|[bmkt])?\b/gi;

function parseOne(num: string, scale: string | undefined): number | null {
  const value = parseFloat(num.replace(/,/g, ""));
  if (Number.isNaN(value)) return null;
  return scale ? value * (SCALE[scale.toLowerCase()] ?? 1) : value;
}

/** All USD amounts found in `text`, normalized to dollars. */
export function parseAmounts(text: string): number[] {
  const out: number[] = [];
  for (const m of text.matchAll(AMOUNT_RE)) {
    const v = parseOne(m[1], m[2]);
    if (v !== null) out.push(v);
  }
  return out;
}

/** The figure to feature for an item: first amount in the headline, else the largest in the body. */
export function keyAmount(headline: string, body: string): number | null {
  const fromHeadline = parseAmounts(headline);
  if (fromHeadline.length) return fromHeadline[0];
  const fromBody = parseAmounts(body);
  return fromBody.length ? Math.max(...fromBody) : null;
}

// Type-aware value (D138). A dollar figure in the text is not automatically *tracked capital*:
// a market-size or forecast number (e.g. "$720B in grid investment needed by 2030") is a
// projection, not money that has actually been awarded, raised, or transacted. Summing those
// into "≈$X tracked" and drawing them as full magnitude bars let one forecast dwarf every real
// deal (a single $720B projection inflated the Energy/AI headline total, 7/9). We keep them —
// nothing is dropped (D129 philosophy) — but classify them so the ledger frames them honestly.
export type AmountKind = "tracked" | "projected";

export interface TypedAmount {
  value: number;
  kind: AmountKind;
}

// Forecast / market-size framing. Kept high-precision on purpose: a bare future year is NOT
// enough (a real award carries a period of performance — "delivery by 2031"), so we require an
// explicit forecast verb or market-size noun.
const PROJECTION_RE =
  /\b(?:projected|forecasts?|forecasted|estimated to (?:reach|hit|grow|total|exceed)|expected to (?:reach|hit|grow|exceed|top|surpass)|could (?:reach|hit|top|exceed|grow to)|poised to (?:reach|hit)|set to (?:reach|hit)|on track to (?:reach|hit)|(?:total )?addressable market|market (?:size|value|worth|opportunity)|\bTAM\b|\bCAGR\b|annually|per year|per annum)\b/i;

// Long-horizon aggregate estimates: an investment/spending/demand figure tied to a future year
// in either order ("$720B of grid investment … by 2030" / "by 2030 … $720B of spending"). The
// bounded gap keeps the match inside one clause so it can't span unrelated sentences.
const HORIZON_RE =
  /\b(?:investment|spending|capex|capital expenditure|buildout|build-out|outlays?|demand|capacity|needed|required)\b[^.]{0,60}\bby\s+20\d\d\b|\bby\s+20\d\d\b[^.]{0,60}\b(?:investment|spending|capex|buildout|build-out|outlays?|demand|capacity|needed|required)\b/i;

function looksProjected(text: string): boolean {
  return PROJECTION_RE.test(text) || HORIZON_RE.test(text);
}

/** The featured figure plus whether it is committed capital or a market/forecast projection (D138).
 * Classifies from the same text the figure was read out of (headline, else body), so a projection
 * mentioned in the body doesn't taint a real headline award (and vice versa). */
export function classifyAmount(headline: string, body: string): TypedAmount | null {
  const fromHeadline = parseAmounts(headline);
  if (fromHeadline.length) {
    return { value: fromHeadline[0], kind: looksProjected(headline) ? "projected" : "tracked" };
  }
  const fromBody = parseAmounts(body);
  if (!fromBody.length) return null;
  return { value: Math.max(...fromBody), kind: looksProjected(body) ? "projected" : "tracked" };
}

/** Compact USD label: $1.5B, $700M, $55.9M, $500K. */
export function formatUsd(value: number): string {
  for (const [unit, label] of [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ] as const) {
    if (value >= unit) {
      const n = value / unit;
      return `$${n % 1 === 0 ? n : n.toFixed(1)}${label}`;
    }
  }
  return `$${value}`;
}
