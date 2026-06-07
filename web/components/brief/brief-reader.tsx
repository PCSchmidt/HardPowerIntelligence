import { AlertTriangle } from "lucide-react";
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
      <BriefContent items={brief.items} citations={brief.citations} />
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
