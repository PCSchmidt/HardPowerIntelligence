import { Activity, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { splitSignal } from "@/lib/signal";

// Renders the GDELT media-attention signal (D082) with a trend arrow + color on each
// momentum delta (D087), replacing the flat dashed text line. Server Component — the
// signal is static text, no interactivity. The disclaimer lives in the string itself, so
// it stays intact; styling only foregrounds the direction of each move.
export function SignalLine({ signal }: { signal: string }) {
  const segments = splitSignal(signal);
  return (
    <section className="mt-8 flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 px-4 py-3 text-ui-sm text-muted-foreground">
      <Activity size={14} className="mt-0.5 shrink-0" />
      <span>
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
    </section>
  );
}
