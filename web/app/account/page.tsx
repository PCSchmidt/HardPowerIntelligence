import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, ExternalLink, ShieldCheck } from "lucide-react";

import { getMe } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";

export const metadata: Metadata = {
  title: "Account",
  robots: { index: false, follow: false },
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <dt className="text-ui-md text-muted-foreground">{label}</dt>
      <dd className="text-ui-md font-medium text-foreground">{value}</dd>
    </div>
  );
}

export default async function AccountPage() {
  const { data: me } = await getMe();

  if (!me) {
    return (
      <div className="mx-auto max-w-content px-4 py-16 sm:px-6">
        <EmptyState
          title="We couldn't load your account."
          hint="Please refresh, or sign out and back in."
        />
      </div>
    );
  }

  const isPro = me.tier === "pro";
  const isComp = me.source === "comp";

  return (
    <div className="mx-auto max-w-card px-4 py-16 sm:px-6">
      <h1 className="font-display text-display-md text-foreground">Account</h1>
      <p className="mt-1 text-ui-md text-muted-foreground">{me.email}</p>

      {/* Plan card */}
      <div className="mt-8 rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between">
          <span className="text-ui-md text-muted-foreground">Plan</span>
          {isPro ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 text-ui-sm font-semibold text-success">
              <ShieldCheck size={14} />
              {isComp ? "PRO · COMPLIMENTARY" : "PRO"}
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-muted px-3 py-1 text-ui-sm font-semibold text-muted-foreground">
              FREE
            </span>
          )}
        </div>

        <dl className="mt-4 divide-y divide-border border-t border-border">
          {isPro && <Row label="Member since" value={fmtDate(me.subscribed_at)} />}
          {isPro && (
            <Row
              label={isComp ? "Access through" : "Renews"}
              value={me.current_period_end ? fmtDate(me.current_period_end) : "—"}
            />
          )}
          {!isPro && <Row label="Status" value="Free — current-day brief only" />}
        </dl>

        {/* Actions */}
        <div className="mt-6">
          {!isPro && (
            <Button size="lg" render={<Link href="/subscribe" />}>
              Upgrade to Pro →
            </Button>
          )}

          {isPro && isComp && (
            <p className="text-ui-md text-muted-foreground">
              You have complimentary Pro access — there&apos;s no billing to manage. Enjoy
              the full archive, entity 360, and PDF export.
            </p>
          )}

          {isPro && !isComp && me.customer_portal_url && (
            <Button
              variant="outline"
              render={
                <a
                  href={me.customer_portal_url}
                  target="_blank"
                  rel="noopener noreferrer"
                />
              }
            >
              Manage subscription
              <ExternalLink size={16} />
            </Button>
          )}

          {isPro && !isComp && !me.customer_portal_url && (
            <p className="text-ui-md text-muted-foreground">
              To update payment or cancel, use the <strong>Manage</strong> link in your
              Lemon Squeezy email receipt. A direct link will appear here after your next
              billing event.
            </p>
          )}
        </div>
      </div>

      {/* Pro benefits reminder for free users */}
      {!isPro && (
        <ul className="mt-8 space-y-2">
          {[
            "90-day searchable archive",
            "Entity 360 pages + follows",
            "PDF export of any brief",
          ].map((b) => (
            <li key={b} className="flex items-center gap-2 text-ui-md text-foreground">
              <CheckCircle2 size={16} className="text-success" />
              {b}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-10 text-ui-sm text-muted-foreground">
        Hard Power Intelligence is a general publication. Nothing here is investment advice.
      </p>
    </div>
  );
}
