import Link from "next/link";
import { Shield } from "lucide-react";

// Site footer (Server Component). Static content.
export function Footer() {
  return (
    <footer className="border-t border-border bg-muted/40">
      <div className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 font-display text-lg font-bold text-brand">
              <Shield size={20} className="text-brand-secondary" />
              Hard Power Intelligence
            </div>
            <p className="max-w-xs text-ui-sm text-muted-foreground">
              Daily cited intelligence for defense, energy, and AI infrastructure.
            </p>
          </div>
          <nav className="flex gap-6 text-ui-sm text-muted-foreground">
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-foreground">
              Privacy
            </Link>
            <Link href="/contact" className="hover:text-foreground">
              Contact
            </Link>
          </nav>
        </div>
        <p className="mt-8 text-ui-xs text-muted-foreground">
          Hard Power Intelligence is a general publication. Nothing published here constitutes
          investment advice.
        </p>
      </div>
    </footer>
  );
}
