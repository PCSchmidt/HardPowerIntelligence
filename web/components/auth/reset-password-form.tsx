"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { MIN_PASSWORD, passwordProblem } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "./password-input";

export function ResetPasswordForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);

  // Reaching this page means /auth/callback exchanged the recovery code for a session. Confirm
  // that actually happened before showing the form: without a session updateUser() would fail
  // with an opaque error after the user typed a new password twice. `null` = still checking, so
  // the form never flashes into view and then vanishes.
  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data }) => setReady(Boolean(data.session)));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const problem = passwordProblem(password, confirm);
    if (problem) {
      setError(problem);
      return;
    }
    setLoading(true);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    // The recovery session is already a full session, so go straight to the product rather
    // than bouncing through /login and making them type the password they just set.
    router.push("/desk/defense");
    router.refresh();
  }

  if (ready === null) {
    return <p className="text-ui-sm text-muted-foreground">Checking your link…</p>;
  }

  if (ready === false) {
    return (
      <div className="space-y-4">
        <p className="text-ui-md text-foreground">
          This reset link is invalid, expired, or already used.
        </p>
        <Link href="/forgot-password" className="block text-ui-sm text-primary hover:underline">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <PasswordInput
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        placeholder="New password"
      />
      <PasswordInput
        value={confirm}
        onChange={setConfirm}
        autoComplete="new-password"
        placeholder="Confirm new password"
      />
      <p className="text-ui-xs text-muted-foreground">At least {MIN_PASSWORD} characters.</p>
      {error && <p className="text-ui-sm text-destructive">{error}</p>}
      <Button type="submit" size="lg" className="w-full" disabled={loading}>
        {loading ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
