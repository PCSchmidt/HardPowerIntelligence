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
      options: { emailRedirectTo: `${window.location.origin}/subscribe` },
    });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    // When email confirmation is disabled, signUp returns a live session — the
    // user is already signed in, so move them into the trial flow. Otherwise a
    // confirmation email was sent.
    if (data.session) {
      router.push("/subscribe");
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
