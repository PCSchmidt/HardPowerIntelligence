"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

// Initiates Lemon Squeezy hosted checkout (D050). Falls back to an explicit
// "not configured" message when the API route reports payments are unset (D045).
export function CheckoutButton({
  variant = "monthly",
  className,
  children,
}: {
  variant?: "monthly" | "annual";
  className?: string;
  children: React.ReactNode;
}) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function startCheckout() {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variant }),
      });
      const body = await res.json();
      if (res.ok && body.url) {
        window.location.href = body.url;
        return;
      }
      setMessage(body.error ?? "Checkout is not available right now.");
    } catch {
      setMessage("Checkout is not available right now.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button size="lg" className={className} disabled={loading} onClick={startCheckout}>
        {loading ? "Starting…" : children}
      </Button>
      {message && <p className="text-ui-sm text-warning">{message}</p>}
    </div>
  );
}
