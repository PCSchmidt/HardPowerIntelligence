import Link from "next/link";
import { AlertTriangle, ArrowRight, Clock, Sparkles } from "lucide-react";
import type { Brief } from "@/lib/types";
import { cn } from "@/lib/utils";
import { BriefHeader } from "./brief-header";
import { BriefGlance } from "./brief-glance";
import { BriefContent } from "./brief-content";
import { SignalLine } from "./signal-line";
import { ReaderOnboarding } from "./reader-onboarding";
import { DeskViewTracker } from "@/components/analytics/desk-view-tracker";
import { FeedbackWidget } from "@/components/feedback/feedback-widget";

// Composes the full reader (Server Component): staleness strip (D013), header,
// interactive content, and the metadata footer. Shared by the desk and archive pages.
export function BriefReader({ brief }: { brief: Brief }) {
  return (
    <div className="mx-auto max-w-content px-4 py-10 sm:px-6">
      <DeskViewTracker
        desk={brief.desk}
        briefDate={brief.date}
        itemCount={brief.items.length}
      />
      <FeedbackWidget />
      <ReaderOnboarding />
      {brief.staleness_indicator && (() => {
        // A quiet day / pre-cron load (latest_available) is informational, not an error — render
        // it neutrally so it reassures rather than alarms; pending/failed stays amber (D013).
        const info = brief.staleness_indicator.current_status === "latest_available";
        const Icon = info ? Clock : AlertTriangle;
        return (
          <div
            className={cn(
              "mb-6 flex items-start gap-2 rounded-md px-4 py-3 text-ui-sm",
              info ? "bg-muted text-muted-foreground" : "bg-warning/10 text-warning",
            )}
          >
            <Icon size={16} className="mt-0.5 shrink-0" />
            <span>{brief.staleness_indicator.message}</span>
          </div>
        );
      })()}
      <BriefHeader brief={brief} />
      <BriefGlance items={brief.items} citations={brief.citations} />
      {brief.convergence_read && (
        <section className="mt-8 rounded-md border border-brand-secondary/30 bg-muted/40 p-5">
          <div className="mb-2 flex items-center gap-2 text-ui-xs font-medium uppercase tracking-wide text-brand-secondary">
            <Sparkles size={14} className="shrink-0" />
            Convergence — HPI interpretation
          </div>
          <p className="prose-brief text-foreground">{brief.convergence_read}</p>
        </section>
      )}
      <BriefContent
        items={brief.items}
        citations={brief.citations}
        entities={brief.entities}
        desk={brief.desk}
      />
      {brief.signal && <SignalLine signal={brief.signal} series={brief.signal_series} />}
      {/* Full Wire (D112): everything material that didn't fit the curated brief, so a heavy
          news day doesn't throw away real signal. */}
      <Link
        href={`/desk/${brief.desk}/wire`}
        className="mt-8 inline-flex items-center gap-1 text-ui-sm font-medium text-primary hover:underline"
      >
        See the full wire — everything that didn&apos;t fit <ArrowRight size={14} />
      </Link>
    </div>
  );
}
