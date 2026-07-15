import { NextResponse, type NextRequest } from "next/server";

import { createSupabaseServerClient } from "@/lib/supabase/server";

// Every emailed auth link lands here (D141). @supabase/ssr uses the PKCE flow, so a
// confirmation / recovery link arrives as a one-time `?code=` that must be exchanged for a
// session cookie server-side. Before this route existed there was nowhere to do that: signup
// pointed `emailRedirectTo` straight at /desk/defense, so a confirmed user landed on the desk
// carrying an unspent code and no session — i.e. still logged out. Password recovery had no
// entry point at all.
//
// `next` is the post-exchange destination (/reset-password for recovery, the desk for signup).
// It is deliberately restricted to same-origin relative paths: this value arrives in a URL we
// put in an email, so treating it as an arbitrary redirect target would make it an open-redirect
// gadget — an attacker-supplied `next` could bounce a freshly-authenticated user off-site.
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/desk/defense";
  return raw;
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));

  // Supabase reports a dead link (expired/already-used) via error params, not the code path.
  const errorDescription = searchParams.get("error_description");
  if (errorDescription) {
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent(errorDescription)}`,
    );
  }

  if (!code) {
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent("That link is missing its code. Request a new one.")}`,
    );
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    // Most common cause: the link expired or was already used (they are single-use).
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent("That link has expired or was already used. Request a new one.")}`,
    );
  }

  return NextResponse.redirect(`${origin}${next}`);
}
