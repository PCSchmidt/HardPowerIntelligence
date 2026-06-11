-- Lock down content tables to the FastAPI data boundary (D011) — closes the
-- Gate 8 MEDIUM finding (SECURITY_AUDIT.md, A01).
--
-- The initial schema granted `SELECT TO authenticated USING (true / status='published')`
-- on the briefs/entities content tables. Because the app reads briefs only through
-- FastAPI (FASTAPI_INTERNAL_URL, D011) — never the browser Supabase client — those
-- grants are unnecessary, and they let a logged-in FREE user call Supabase PostgREST
-- directly with their JWT + the public anon key to read the entire published archive,
-- bypassing the Pro/archive paywall (D012). Revenue leak, not a PII breach.
--
-- Fix: remove all client (anon/authenticated) read access to the content tables.
-- FastAPI connects via the direct Postgres role (DATABASE_URL, asyncpg) which bypasses
-- RLS and table grants, so the API is unaffected. With RLS enabled and no remaining
-- permissive policy, these tables are deny-all to PostgREST clients — defense in depth
-- alongside the explicit REVOKE.
--
-- NOTE: This assumes no client-side direct reads of this data. Entity 360 / brief
-- rendering all flow through FastAPI per D011. If a future feature needs direct client
-- reads, add a deliberate, tier-aware policy then.

-- Drop the permissive client read policies (service_role/postgres bypass RLS regardless).
DROP POLICY IF EXISTS briefs_auth_read       ON briefs;
DROP POLICY IF EXISTS brief_items_auth_read   ON brief_items;
DROP POLICY IF EXISTS citations_auth_read      ON citations;
DROP POLICY IF EXISTS entities_auth_read       ON entities;
DROP POLICY IF EXISTS entity_edges_auth_read   ON entity_edges;

-- Belt-and-suspenders: revoke the default PostgREST SELECT grants on these tables.
REVOKE SELECT ON briefs        FROM anon, authenticated;
REVOKE SELECT ON brief_items   FROM anon, authenticated;
REVOKE SELECT ON citations     FROM anon, authenticated;
REVOKE SELECT ON entities      FROM anon, authenticated;
REVOKE SELECT ON entity_edges  FROM anon, authenticated;
