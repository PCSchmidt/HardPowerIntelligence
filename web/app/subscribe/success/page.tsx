import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Welcome to Pro",
  robots: { index: false, follow: false },
};

export default function SubscribeSuccessPage() {
  return (
    <div className="mx-auto max-w-card px-4 py-24 text-center">
      <CheckCircle2 size={40} className="mx-auto text-success" />
      <h1 className="mt-4 font-display text-display-md text-foreground">You&apos;re on Pro.</h1>
      <p className="mt-2 text-ui-md text-muted-foreground">
        Archive access, entity 360, and PDF export are now unlocked.
      </p>
      <div className="mt-8 flex justify-center">
        <Button size="lg" render={<Link href="/desk/defense" />}>
          Go to the Defense Desk →
        </Button>
      </div>
    </div>
  );
}
