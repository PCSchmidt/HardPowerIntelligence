import { CheckCircle2 } from "lucide-react";
import type { Brief } from "@/lib/types";
import { stripCiteMarkers } from "@/lib/utils";

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

// Brief masthead (Server Component): desk label, date, faithfulness badge,
// headline, and BLUF.
export function BriefHeader({ brief }: { brief: Brief }) {
  return (
    <header className="space-y-4 border-b border-border pb-8">
      <div className="flex flex-wrap items-center gap-3 text-ui-sm text-muted-foreground">
        <span className="rounded-sm bg-desk-defense px-2 py-0.5 font-medium uppercase tracking-wide text-white">
          {brief.desk}
        </span>
        <span>{formatDate(brief.date)}</span>
        {brief.faithfulness_score != null && (
          <span className="inline-flex items-center gap-1 rounded-sm bg-success/10 px-2 py-0.5 font-medium text-success">
            <CheckCircle2 size={14} />
            {Math.round(brief.faithfulness_score * 100)}% cited
          </span>
        )}
      </div>
      <h1 className="font-display text-display-lg text-foreground">{brief.headline}</h1>
      {brief.bluf && (
        <p className="border-l-2 border-brand-secondary pl-4 font-body text-body-lg text-foreground">
          {stripCiteMarkers(brief.bluf)}
        </p>
      )}
    </header>
  );
}
