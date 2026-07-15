"use client";

import { useState } from "react";
import Link from "next/link";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
    });
    setLoading(false);
    // Only surface transport-level failures (offline, rate limit). A "no such user" is NOT
    // reported: answering that question differently for a registered vs unregistered address
    // turns this box into an account-enumeration oracle. Supabase already returns success for
    // unknown addresses; the identical confirmation below keeps it that way.
    if (error && error.status !== 400) {
      setError(error.message);
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <div className="space-y-4">
        <p className="text-ui-md text-foreground">
          If an account exists for <span className="font-medium">{email}</span>, a reset link is on
          its way. The link is single-use and expires in an hour.
        </p>
        <p className="text-ui-sm text-muted-foreground">
          Nothing arriving? Check spam, then try again in a few minutes.
        </p>
        <Link href="/login" className="block text-ui-sm text-primary hover:underline">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        autoComplete="email"
        placeholder="Email"
        required
        className="h-10 w-full rounded-md border border-input bg-card px-3 text-ui-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {error && <p className="text-ui-sm text-destructive">{error}</p>}
      <Button type="submit" size="lg" className="w-full" disabled={loading || !email}>
        {loading ? "Sending…" : "Send reset link"}
      </Button>
      <p className="text-center text-ui-sm text-muted-foreground">
        Remembered it?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
