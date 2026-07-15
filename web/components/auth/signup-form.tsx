"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "./password-input";
import { OAuthButtons } from "./oauth-buttons";

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      // Route the confirmation link through /auth/callback (D141), not straight at the desk:
      // the emailed link carries a PKCE `code` that only the callback can exchange for a
      // session, so pointing it at /desk/defense landed confirmed users there still logged out.
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback?next=/desk/defense`,
      },
    });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    // Land new users on the product (today's free brief), not the /subscribe paywall —
    // a free account already sees the full current-day brief, so leading with the
    // upgrade page (which reads as "you must pay", and shows "not configured" until
    // Lemon Squeezy is live) was confusing. When email confirmation is disabled signUp
    // returns a live session; otherwise a confirmation email was sent.
    if (data.session) {
      router.push("/desk/defense");
      router.refresh();
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <p className="text-center text-ui-md text-foreground">
        Check your email to confirm your account.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="space-y-4">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="Email"
          className="h-10 w-full rounded-md border border-input bg-card px-3 text-ui-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" />
        {error && <p className="text-ui-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <div className="flex items-center gap-3 text-ui-sm text-muted-foreground">
        <div className="h-px flex-1 bg-border" />
        or continue with
        <div className="h-px flex-1 bg-border" />
      </div>
      <OAuthButtons />

      <p className="text-center text-ui-xs text-muted-foreground">
        By signing up you agree to our{" "}
        <Link href="/terms" className="underline">
          Terms
        </Link>{" "}
        and{" "}
        <Link href="/privacy" className="underline">
          Privacy Policy
        </Link>
        .
      </p>
      <p className="text-center text-ui-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
