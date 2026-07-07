-- Enable RLS on the operational / reference tables the initial schema left uncovered (D134).
--
-- The Supabase security advisor flagged these five as `rls_disabled_in_public` (CRITICAL): a
-- public-schema table with RLS *off* is readable/writable by anyone holding the project's anon
-- key via PostgREST. They were created without RLS (initial_schema enabled it on the 11 content/
-- user tables; brief_wire got it in D112 — these five slipped through).
--
-- These tables are read ONLY server-side: FastAPI (calendar.py, run_health.py) and the ingest
-- worker connect via the direct Postgres role (DATABASE_URL, asyncpg) which BYPASSES RLS, and the
-- web browser never reads them directly (no supabase.from() calls anywhere — data flows through
-- FastAPI per D011). So the correct, secure state is **RLS enabled with NO policy**: deny-all to
-- anon/authenticated, fully unaffected for the API/worker. Same pattern as brief_wire (D112) and
-- the lock_briefs content tables (Gate 8). No policy is needed unless a future feature wants
-- deliberate client-side reads (add a tier-aware one then).
--
-- Idempotent + drift-fix: this mirrors SQL already applied by hand in production, so it re-runs
-- as a no-op there (ENABLE RLS on an already-enabled table does nothing; REVOKE of an absent grant
-- does nothing) while bringing the repo back in sync so a fresh env / DB reset reproduces it.

ALTER TABLE entity_identifiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_aliases     ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_registry    ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE calendar_events    ENABLE ROW LEVEL SECURITY;

-- Belt-and-suspenders (REVOKE ALL, not just SELECT — the advisor warns these were also writable):
-- with RLS on there's no permissive policy so PostgREST is already deny-all, but strip the grants too.
REVOKE ALL ON entity_identifiers FROM anon, authenticated;
REVOKE ALL ON entity_aliases     FROM anon, authenticated;
REVOKE ALL ON source_registry    FROM anon, authenticated;
REVOKE ALL ON ingestion_runs     FROM anon, authenticated;
REVOKE ALL ON calendar_events    FROM anon, authenticated;
