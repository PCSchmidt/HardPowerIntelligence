"use client";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

// Google + GitHub OAuth (D018). Functional; providers must be enabled in Supabase.
export function OAuthButtons() {
  async function signInWith(provider: "google" | "github") {
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/desk/defense` },
    });
  }

  return (
    <div className="space-y-2">
      <Button variant="outline" size="lg" className="w-full" onClick={() => signInWith("google")}>
        Continue with Google
      </Button>
      <Button variant="outline" size="lg" className="w-full" onClick={() => signInWith("github")}>
        Continue with GitHub
      </Button>
    </div>
  );
}
