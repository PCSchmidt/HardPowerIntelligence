// Split the GDELT signal line into renderable segments (D087). The signal string is
// built server-side (engine/signal/gdelt.py build_signal_line) as labeled, disclaimed
// prose carrying "+N%" / "-N%" momentum tokens. We split on those tokens so the reader
// can render a trend arrow + color per delta without re-deriving the number — the text
// stays authoritative; this is presentation only.

export type SignalSegment =
  | { kind: "text"; text: string }
  | { kind: "delta"; text: string; direction: "up" | "down" };

const DELTA_RE = /([+-]\d+(?:\.\d+)?%)/g;

export function splitSignal(signal: string): SignalSegment[] {
  const segments: SignalSegment[] = [];
  let last = 0;
  for (const m of signal.matchAll(DELTA_RE)) {
    const idx = m.index ?? 0;
    if (idx > last) segments.push({ kind: "text", text: signal.slice(last, idx) });
    const token = m[1];
    segments.push({ kind: "delta", text: token, direction: token.startsWith("-") ? "down" : "up" });
    last = idx + token.length;
  }
  if (last < signal.length) segments.push({ kind: "text", text: signal.slice(last) });
  return segments;
}
