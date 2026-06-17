// Parse the key dollar figure out of brief text for the at-a-glance magnitude bars (D084).
// The headline carries the salient number ("…for $55.9M", "…$700M Subscription"), so we read
// the headline first and fall back to the largest figure in the body. Display-only; the
// authoritative facts remain the cited body text.
const SCALE: Record<string, number> = {
  trillion: 1e12,
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
