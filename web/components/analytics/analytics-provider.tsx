"use client";

import { Suspense, useEffect } from "react";
import { usePathname } from "next/navigation";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { capturePageview, identify, initAnalytics, resetIdentity } from "@/lib/analytics";

// Deliberately uses usePathname and NOT useSearchParams. Two reasons, and the second is the
// important one: (a) useSearchParams forces a Suspense boundary or it opts the whole tree into
// client rendering; (b) HPI has no analytics worth reading in a query string, but /auth/callback
// carries single-use auth codes in one — so the safest handling of the search string is to never
// touch it. lib/analytics strips it again on the way out, belt and braces.
function PageviewTracker() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname) capturePageview(pathname);
  }, [pathname]);

  return null;
}

export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initAnalytics();
  }, []);

  // Tie events to a durable identity so "return visits" is answerable. getSession() reads local
  // storage — no network, no error when signed out (same pattern as the navbar).
  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data }) => {
      if (data.session?.user) identify(data.session.user.id);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (session?.user) identify(session.user.id);
      else if (event === "SIGNED_OUT") resetIdentity();
    });
    return () => subscription.unsubscribe();
  }, []);

  return (
    <>
      <Suspense fallback={null}>
        <PageviewTracker />
      </Suspense>
      {children}
    </>
  );
}
