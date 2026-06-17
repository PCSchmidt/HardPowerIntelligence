import { Activity, AlertTriangle, Sparkles } from "lucide-react";
import type { Brief } from "@/lib/types";
import { BriefHeader } from "./brief-header";
import { BriefContent } from "./brief-content";

// Composes the full reader (Server Component): staleness strip (D013), header,
// interactive content, and the metadata footer. Shared by the desk and archive pages.
export function BriefReader({ brief }: { brief: Brief }) {
  return (
    <div className="mx-auto max-w-content px-4 py-10 sm:px-6">
      {brief.staleness_indicator && (
        <div className="mb-6 flex items-start gap-2 rounded-md bg-warning/10 px-4 py-3 text-ui-sm text-warning">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{brief.staleness_indicator.message}</span>
        </div>
      )}
      <BriefHeader brief={brief} />
      {brief.convergence_read && (
        <section className="mt-8 rounded-md border border-brand-secondary/30 bg-muted/40 p-5">
          <div className="mb-2 flex items-center gap-2 text-ui-xs font-medium uppercase tracking-wide text-brand-secondary">
            <Sparkles size={14} className="shrink-0" />
            Convergence — HPI interpretation
          </div>
          <p className="prose-brief text-foreground">{brief.convergence_read}</p>
        </section>
      )}
      <BriefContent items={brief.items} citations={brief.citations} />
      {brief.signal && (
        <section className="mt-8 flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 px-4 py-3 text-ui-sm text-muted-foreground">
          <Activity size={14} className="mt-0.5 shrink-0" />
          <span>{brief.signal}</span>
        </section>
      )}
      <footer className="mt-8 border-t border-border pt-4 text-ui-sm text-muted-foreground">
        {brief.model_waterfall.synthesis_model && (
          <span>Synthesis: {brief.model_waterfall.synthesis_model}</span>
        )}
        {brief.faithfulness_score != null && (
          <span> · Eval score: {brief.faithfulness_score.toFixed(2)}</span>
        )}
      </footer>
    </div>
  );
}
