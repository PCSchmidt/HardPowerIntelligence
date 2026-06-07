import Link from "next/link";
import { Lock } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

// Full-page Pro gate (D024) — shown for archived briefs / entity 360 to free users.
export function ArchiveLock({
  title = "This content requires Pro",
  body,
  teaser,
}: {
  title?: string;
  body: string;
  teaser?: string;
}) {
  return (
    <div className="mx-auto max-w-card px-4 py-20 text-center">
      {teaser && <p className="mb-6 font-display text-display-sm text-muted-foreground">{teaser}</p>}
      <div className="rounded-xl border border-border bg-card p-10 shadow-sm">
        <Lock size={40} className="mx-auto text-brand-secondary" />
        <h1 className="mt-4 font-display text-display-md text-foreground">{title}</h1>
        <p className="mt-2 text-ui-md text-muted-foreground">{body}</p>
        <div className="mt-6 flex justify-center">
          <Link href="/subscribe" className={buttonVariants({ size: "lg" })}>
            Start 14-day free trial
          </Link>
        </div>
      </div>
    </div>
  );
}
