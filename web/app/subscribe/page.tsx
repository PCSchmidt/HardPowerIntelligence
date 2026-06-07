import type { Metadata } from "next";
import { PricingTable } from "@/components/subscription/pricing-table";

export const metadata: Metadata = {
  title: "Subscribe",
  description:
    "14-day free trial. Daily cited defense intelligence briefs. Cancel anytime.",
  robots: { index: true, follow: true },
};

const FAQ = [
  {
    q: "What happens after my trial?",
    a: "After 14 days, your subscription converts to $19/month (or $179/year if you chose annual). Cancel anytime before then and you won't be charged.",
  },
  {
    q: "Can I cancel?",
    a: "Yes, anytime, from your account settings via the customer portal. Access continues until the end of your billing period.",
  },
  {
    q: "What's included in Free?",
    a: "The full current-day brief, every day. Pro adds the 90-day archive, entity 360 pages, PDF export, and follows.",
  },
  {
    q: "Is this investment advice?",
    a: "No. Hard Power Intelligence is a general publication. Nothing here constitutes investment advice.",
  },
];

export default function SubscribePage() {
  return (
    <div className="mx-auto max-w-page px-4 py-20 sm:px-6 lg:px-8">
      <h1 className="text-center font-display text-display-lg text-foreground">
        Start your 14-day free trial
      </h1>
      <p className="mx-auto mt-3 max-w-xl text-center text-body-lg text-muted-foreground">
        Daily cited defense intelligence. Credit card required, cancel anytime.
      </p>

      <div className="mt-12">
        <PricingTable />
      </div>

      <div className="mx-auto mt-20 max-w-2xl">
        <h2 className="font-display text-display-md">Frequently asked</h2>
        <dl className="mt-6 divide-y divide-border">
          {FAQ.map(({ q, a }) => (
            <div key={q} className="py-5">
              <dt className="font-display text-display-sm text-foreground">{q}</dt>
              <dd className="mt-2 text-ui-md text-muted-foreground">{a}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
