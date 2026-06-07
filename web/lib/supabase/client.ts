import { createBrowserClient } from "@supabase/ssr";

// Browser Supabase client — used only for auth (D011). Application data goes
// through FastAPI, never supabase-js.
export function createSupabaseBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
