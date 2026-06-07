import { Check, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { CheckoutButton } from "./checkout-button";

const FEATURES: { label: string; free: boolean; pro: boolean }[] = [
  { label: "Daily brief — current day, full content", free: true, pro: true },
  { label: "Brief archive — rolling 90 days", free: false, pro: true },
  { label: "Entity 360 pages", free: false, pro: true },
  { label: "PDF export", free: false, pro: true },
  { label: "Follows & personalization", free: false, pro: true },
];

function Cell({ on }: { on: boolean }) {
  return on ? (
    <Check size={18} className="text-success" />
  ) : (
    <Minus size={18} className="text-muted-foreground/50" />
  );
}

// Free vs Pro comparison (used on marketing home and /subscribe).
export function PricingTable() {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
        <h3 className="font-display text-display-sm">Free</h3>
        <p className="mt-1 text-ui-md text-muted-foreground">Today&apos;s brief, every day.</p>
        <p className="mt-4 font-display text-display-md">$0</p>
        <ul className="mt-6 space-y-3">
          {FEATURES.map((f) => (
            <li key={f.label} className="flex items-center gap-3 text-ui-md">
              <Cell on={f.free} />
              <span className={cn(!f.free && "text-muted-foreground")}>{f.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl border-2 border-brand bg-card p-8 shadow-md">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-display-sm text-brand">Pro</h3>
          <span className="rounded-sm bg-brand-secondary px-2 py-0.5 text-ui-xs font-medium uppercase tracking-wide text-brand">
            14-day trial
          </span>
        </div>
        <p className="mt-1 text-ui-md text-muted-foreground">Archive, entity 360, PDF, follows.</p>
        <p className="mt-4 font-display text-display-md">
          $19<span className="text-ui-md font-normal text-muted-foreground">/month</span>
        </p>
        <p className="text-ui-sm text-muted-foreground">or $179/year — save 21%</p>
        <ul className="mt-6 space-y-3">
          {FEATURES.map((f) => (
            <li key={f.label} className="flex items-center gap-3 text-ui-md">
              <Cell on={f.pro} />
              <span>{f.label}</span>
            </li>
          ))}
        </ul>
        <div className="mt-8">
          <CheckoutButton variant="monthly" className="w-full">
            Start 14-day free trial
          </CheckoutButton>
          <p className="mt-2 text-ui-xs text-muted-foreground">
            Credit card required. Cancel anytime. $19/month after trial.
          </p>
        </div>
      </div>
    </div>
  );
}
