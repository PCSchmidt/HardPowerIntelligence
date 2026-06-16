"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, Shield } from "lucide-react";
import type { User } from "@supabase/supabase-js";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const DESKS = [
  { label: "Defense", href: "/desk/defense", active: true },
  { label: "Energy", href: "/desk/energy", active: true },
  { label: "AI Infrastructure", href: "/desk/ai", active: true },
];

export function NavBar() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    // getSession() reads local storage (no network, no error when signed out).
    supabase.auth.getSession().then(({ data }) => setUser(data.session?.user ?? null));
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user ?? null));
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function signOut() {
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signOut();
    setMenuOpen(false);
    router.push("/");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 font-display text-lg font-bold text-brand">
          <Shield size={20} className="text-brand-secondary" />
          HPI
        </Link>

        <nav className="hidden items-center gap-1 lg:flex">
          {DESKS.map((desk) =>
            desk.active ? (
              <Link
                key={desk.label}
                href={desk.href}
                className="rounded-md px-3 py-1.5 text-ui-md font-medium text-foreground hover:bg-muted"
              >
                {desk.label}
              </Link>
            ) : (
              <span
                key={desk.label}
                title="Coming soon"
                className="cursor-default rounded-md px-3 py-1.5 text-ui-md text-muted-foreground/60"
              >
                {desk.label}
              </span>
            ),
          )}
        </nav>

        <div className="flex items-center gap-2">
          {user ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-ui-md hover:bg-muted"
                aria-expanded={menuOpen}
              >
                <span className="max-w-[14ch] truncate">{user.email}</span>
                <ChevronDown size={16} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-1 w-52 rounded-lg border border-border bg-popover p-1 shadow-md">
                  <Link
                    href="/account"
                    className="block rounded-md px-3 py-2 text-ui-md hover:bg-muted"
                    onClick={() => setMenuOpen(false)}
                  >
                    Account settings
                  </Link>
                  <Link
                    href="/subscribe"
                    className="block rounded-md px-3 py-2 text-ui-md hover:bg-muted"
                    onClick={() => setMenuOpen(false)}
                  >
                    Upgrade to Pro
                  </Link>
                  <button
                    type="button"
                    onClick={signOut}
                    className="block w-full rounded-md px-3 py-2 text-left text-ui-md hover:bg-muted"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <Link
                href="/login"
                className={cn("rounded-md px-3 py-1.5 text-ui-md font-medium hover:bg-muted")}
              >
                Sign in
              </Link>
              <Link href="/signup" className={buttonVariants({ size: "lg" })}>
                Start free trial
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
