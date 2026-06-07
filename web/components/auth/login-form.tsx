"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "./password-input";
import { OAuthButtons } from "./oauth-buttons";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push(searchParams.get("next") ?? "/desk/defense");
    router.refresh();
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
        <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" />
        <div className="text-right">
          <Link href="/forgot-password" className="text-ui-sm text-muted-foreground hover:text-foreground">
            Forgot password?
          </Link>
        </div>
        {error && <p className="text-ui-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <div className="flex items-center gap-3 text-ui-sm text-muted-foreground">
        <div className="h-px flex-1 bg-border" />
        or continue with
        <div className="h-px flex-1 bg-border" />
      </div>
      <OAuthButtons />

      <p className="text-center text-ui-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="font-medium text-primary hover:underline">
          Start free trial
        </Link>
      </p>
    </div>
  );
}
