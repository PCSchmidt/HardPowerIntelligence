import { Activity, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { splitSignal } from "@/lib/signal";
import type { SignalSeries } from "@/lib/types";

// A minimal inline sparkline (D089) of the lead theme's ~6-week GDELT volume series,
// colored by trend. Pure SVG polyline — no chart library, no client JS. Returns nothing
// for a too-short series so a sparse signal degrades to just the line.
function Sparkline({ series, direction }: { series: number[]; direction: "up" | "down" | null }) {
  if (series.length < 2) return null;
  const w = 88;
  const h = 22;
  const pad = 2;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const points = series
    .map((v, i) => {
      const x = pad + (i / (series.length - 1)) * (w - 2 * pad);
      const y = pad + (1 - (v - min) / range) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const color =
    direction === "down"
      ? "text-destructive"
      : direction === "up"
        ? "text-success"
        : "text-muted-foreground";
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className={cn("mt-0.5 shrink-0", color)}
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Renders the GDELT media-attention signal (D082) with a trend arrow + color on each
// momentum delta (D087) and a lead-theme sparkline (D089), replacing the flat dashed line.
// Server Component — static text + SVG, no interactivity. The disclaimer lives in the
// string itself, so it stays intact; styling only foregrounds direction of each move.
export function SignalLine({ signal, series }: { signal: string; series?: SignalSeries | null }) {
  const segments = splitSignal(signal);
  return (
    <section className="mt-8 flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 px-4 py-3 text-ui-sm text-muted-foreground">
      <Activity size={14} className="mt-0.5 shrink-0" />
      <span className="flex-1">
        {segments.map((seg, i) =>
          seg.kind === "delta" ? (
            <span
              key={i}
              className={cn(
                "mx-0.5 inline-flex items-center gap-0.5 rounded-sm px-1 font-medium tabular-nums",
                seg.direction === "up"
                  ? "bg-success/10 text-success"
                  : "bg-destructive/10 text-destructive",
              )}
            >
              {seg.direction === "up" ? (
                <TrendingUp size={12} className="shrink-0" />
              ) : (
                <TrendingDown size={12} className="shrink-0" />
              )}
              {seg.text}
            </span>
          ) : (
            <span key={i}>{seg.text}</span>
          ),
        )}
      </span>
      {series && series.series.length >= 2 && (
        <Sparkline series={series.series} direction={series.direction} />
      )}
    </section>
  );
}
