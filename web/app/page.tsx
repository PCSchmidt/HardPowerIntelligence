import Link from "next/link";
import { FileText, Landmark, ShieldCheck } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PricingTable } from "@/components/subscription/pricing-table";

export const revalidate = 3600;

const DIFFERENTIATORS = [
  {
    icon: ShieldCheck,
    title: "Every claim cites its source",
    body: "Each sentence passes a citation-faithfulness eval gate before publish. No claim ships without a verifiable source.",
  },
  {
    icon: Landmark,
    title: "Government data, synthesized",
    body: "Built on free public sources — USAspending, SEC EDGAR, DoD contracts. No paywalled feeds, no black boxes.",
  },
  {
    icon: FileText,
    title: "Sector specificity",
    body: "Defense, energy, and AI infrastructure — not generic finance news. Built for analysts who need depth.",
  },
];

export default function Home() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-background">
        <div className="mx-auto max-w-page px-4 py-24 text-center sm:px-6 lg:px-8">
          <h1 className="mx-auto max-w-3xl font-display text-display-xl text-foreground">
            Intelligence that cites its sources.
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-body-lg text-muted-foreground">
            Daily cited briefings on defense, energy, and AI infrastructure. Every claim links to
            the public record it came from.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link href="/signup" className={buttonVariants({ size: "lg" })}>
              Start 14-day free trial
            </Link>
            <Link
              href="/desk/defense"
              className={buttonVariants({ size: "lg", variant: "outline" })}
            >
              See a sample brief
            </Link>
          </div>
        </div>
      </section>

      {/* Sample brief preview */}
      <section className="border-y border-border bg-muted/30">
        <div className="mx-auto max-w-content px-4 py-16 sm:px-6">
          <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
            <div className="flex items-center gap-2 text-ui-xs font-medium uppercase tracking-wide text-muted-foreground">
              <span className="size-2 rounded-full bg-item-award" /> Award
            </div>
            <h3 className="mt-3 font-display text-display-sm">
              Lockheed Martin Awarded $1.1B LRASM Production Contract
            </h3>
            <p className="prose-brief mt-3">
              The Navy awarded Lockheed Martin a $1.1 billion contract for Long Range Anti-Ship
              Missile production
              <span className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-sm bg-primary/10 px-1 align-super text-[0.65rem] font-medium text-primary">
                1
              </span>
              .
            </p>
            <p className="mt-4 text-ui-sm text-muted-foreground">Source: USAspending.gov</p>
          </div>
          <p className="mt-6 text-center text-ui-md text-muted-foreground">
            <Link href="/signup" className="font-medium text-primary hover:underline">
              Sign up to read the full brief →
            </Link>
          </p>
        </div>
      </section>

      {/* Differentiators */}
      <section className="mx-auto max-w-page px-4 py-20 sm:px-6 lg:px-8">
        <div className="grid gap-10 md:grid-cols-3">
          {DIFFERENTIATORS.map(({ icon: Icon, title, body }) => (
            <div key={title} className="space-y-3">
              <Icon size={24} className="text-brand" />
              <h3 className="font-display text-display-sm">{title}</h3>
              <p className="text-ui-md text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="border-t border-border bg-muted/30">
        <div className="mx-auto max-w-page px-4 py-20 sm:px-6 lg:px-8">
          <h2 className="mb-10 text-center font-display text-display-lg">Simple pricing</h2>
          <PricingTable />
        </div>
      </section>
    </div>
  );
}
